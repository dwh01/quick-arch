"""CoordSys class manages 3d to 2d transforms"""
import mathutils
from mathutils import Matrix, Vector
import bpy, bmesh
from bmesh.types import BMVert, BMFace
import functools
import operator


def approx(a, b):
    """Check two values equal"""
    eps = 1e-4  # 0.1 mm in real units
    return abs(a-b) <= eps


def approx_vector(v, w):
    """Check two vectors equal"""
    eps = 1e-4  # 0.1 mm in real units
    for a, b in zip(v, w):
        if not approx(a, b):
            return False
    return True


def ppstr(v):
    """Pretty string for vector"""
    fmt = '{:.3f}'
    s = [fmt.format(a) for a in v]
    return "<{}>".format(s)


class SmartPoint:
    """Wrapper to track BMVert and 3d/2d coordinates"""
    def __init__(self, pt, break_link=False):
        """
        :param pt: point to capture
        :type pt: Vector(2) or Vector(3) or BMVert, or SmartPoint
        """
        self.bm_vert = None
        if isinstance(pt, BMVert):
            if not break_link:
                self.bm_vert = pt
            self.co3 = pt.co
            self.co2 = None
        elif isinstance(pt, SmartPoint):
            if not break_link:
                self.bm_vert = pt.bm_vert
            if pt.co3:
                self.co3 = pt.co3
                self.co2 = None
            else:
                self.co3 = None
                self.co2 = pt.co2
        elif len(pt) == 3:
            self.co3 = Vector(pt)
            self.co2 = None
        else:
            self.co3 = None
            self.co2 = Vector(pt)

    def __str__(self):
        a = "Invalid 3D"
        b = "Invalid 2D"
        c = "No BMVert"
        if self.co3:
            a = ppstr(self.co3)
        if self.co2:
            b = ppstr(self.co2)
        if self.bm_vert:
            c = "BMVert {}".format(self.bm_vert.index)
        return "Point {}, {}, {}".format(a, b, c)

    def __add__(self, other):
        assert self.co3, "__add__ only works in 3d"
        if isinstance(other, Vector):
            if len(other) == 3:
                return self.co3 + other
        elif isinstance(other, SmartPoint):
            return self.co3 + other.co3
        raise TypeError("Expected Vector(3)")

    def __sub__(self, other):
        assert self.co3, "__sub__ only works in 3d"
        if isinstance(other, Vector):
            if len(other) == 3:
                return self.co3 - other
        elif isinstance(other, SmartPoint):
            return self.co3 - other.co3
        raise TypeError("Expected Vector(3)")

    def __eq__(self, other):
        assert self.co3, "__eq__ only works in 3d"
        if isinstance(other, Vector):
            if len(other) == 3:
                return approx_vector(self.co3, other)
        elif isinstance(other, SmartPoint):
            return approx_vector(self.co3, other.co3)
        raise TypeError("Expected Vector(3)")


class CoordSys:
    X = Vector((1,0,0))
    Y = Vector((0,1,0))
    Z = Vector((0,0,1))

    def __init__(self, mm, face=None, radial=None, normal=None, origin=None):
        """Coordinate system linked to face if provided, or using radial and normal cues
        :param ManagedMesh mm: object needed to get face data layer keys
        :param face: reference face [optional]
        :type face: BMFace or None
        :param radial: for y direction if no face provided (radial in for a frame of polygons)
        :type radial: Vector(3) or None
        :param normal: if no face provided
        :type normal: Vector(3) or None
        :param origin: used if no face is provided to set origin
        :type origin: Vector(3) or None
        :return: None
        """
        self.mm = mm  # hold this for mm,key_xxx access on face
        self.reference_face = face
        # last resort global
        self.xdir = self.X
        self.ydir = self.Y
        self.normal = self.Z
        if origin:
            self.origin = Vector(origin)
        else:
            self.origin = Vector((0,0,0))

        # now try to do better
        if face:
            self.origin = face.calc_center_median()
            if radial is None:
                radial = face[mm.key_radial]
                if radial.length == 0:
                    radial = None
            if normal is None:
                face.normal_update()
                if face.normal.length:
                    normal = face.normal

        if normal:
            self.normal = Vector(normal)
        if not approx(self.normal.length, 1):
            print("bad normal: face, radial, origin=", face, radial, origin)
            self.normal = self.Z
        if approx(1, abs(self.Z.dot(self.normal))):
            # special case depends on context of creation
            if radial:  # context points toward inside
                self.xdir = radial.cross(self.normal)  # radial may not be in plane
                if self.xdir.length == 0:
                    self.xdir = self.X
                else:
                    self.xdir.normalize()
                self.ydir = self.normal.cross(self.xdir)
            else:  # last resort global
                pass
        else:
            if radial:  # context points toward inside
                self.xdir = radial.cross(self.normal)
                if self.xdir.length == 0:
                    # on sloped face, x is in global xy plane and in face plane
                    self.xdir = self.Z.cross(self.normal).normalized()
                    self.ydir = self.normal.cross(self.xdir).normalized()
                else:
                    self.xdir.normalize()
                    self.ydir = self.normal.cross(self.xdir).normalized()
            else:
                # on sloped face, x is in global xy plane and in face plane
                self.xdir = self.Z.cross(self.normal).normalized()
                self.ydir = self.normal.cross(self.xdir).normalized()


        # convert from global to our rotated coordinates
        self.matrix = Matrix.Identity(3)
        self.matrix[0] = self.xdir
        self.matrix[1] = self.ydir
        self.matrix[2] = self.normal
        self.inverse = self.matrix.inverted()

        # now setup 2d offset
        self.origin2d = Vector((0,0))

    def __str__(self):
        s = "Origin " + ppstr(self.origin) + " Mat:\n" + str(self.matrix)
        return s

    def apply_rotation_matrix(self, mat):
        """Apply matrix to update pointing
        :param Matrix mat: transformation matrix(4x4)
        """
        self.matrix = mat @ self.matrix
        self.xdir = Vector(self.matrix[0])
        self.ydir = Vector(self.matrix[1])
        self.normal = Vector(self.matrix[2])
        self.inverse = self.matrix.inverted()

    def copy(self):
        return CoordSys(self.mm, self.reference_face, self.ydir, self.normal, self.origin)

    def flip_normal(self):
        """Flip normal around x"""
        self.ydir = -self.ydir
        self.normal = -self.normal
        self.matrix[1] = self.ydir
        self.matrix[2] = self.normal
        self.inverse = self.matrix.inverted()

    def make_2d(self, v3):
        """Convert 3d point to 2d in this coord sys
        :param v3: point in global coordinates
        :type v3: Vector(3) or SmartPoint
        :return: point in 2d relative coordinates
        :rtype: Vector(2)"""
        if isinstance(v3, SmartPoint):
            if v3.co3:
                v3 = v3.co3
            else:
                raise TypeError('SmartPoint has invalid 3d coordinates')
        elif not (isinstance(v3, Vector) and (len(v3) == 3)):
            raise TypeError('Expected a Vector(3)')

        r3 = self.matrix @ (v3 - self.origin)
        r2 = r3.to_2d() - self.origin2d
        return r2

    def make_3d(self, v2):
        """Convert 2d point to 3d in this coord sys
        :param v2: point in 2d relative coordinates
        :type v2: Vector(2) or SmartPoint
        :return: point in global coordinates
        :rtype: Vector(3)"""
        if isinstance(v2, SmartPoint):
            if v2.co2:
                v2 = v2.co2
            else:
                raise TypeError('SmartPoint has invalid 2d coordinates')
        elif not (isinstance(v2, Vector) and (len(v2) == 2)):
            raise TypeError('Expected a Vector(2) not {}'.format(v2))

        v3 = (v2 + self.origin2d).to_3d()
        r3 = (self.inverse @ v3) + self.origin
        return r3

    def __matmul__(self, other):
        """Shorthand to convert vectors with @ operator"""
        if isinstance(other, Vector):
            if len(other) == 3:
                return self.make_2d(other)
            else:
                return self.make_3d(other)
        raise TypeError("Expected vector(3) for matrix multiply")

    def shift_origin2d(self, v2: Vector):
        """Move 2d origin"""
        self.origin2d += v2

    def shift_origin3d(self, v3: Vector):
        """Move 3d origin"""
        self.origin += v3

    def first_corner_index(self, pts):
        """Find index of point with lowest x (and lowest y if a tie)"""
        lst = [(i, self.make_2d(p)) for i, p in enumerate(pts)]
        lst = [(i, round(1000*p.x), round(1000*p.y)) for i, p in lst]
        lst.sort(key=lambda p: p[2])
        lst.sort(key=lambda p: p[1])
        first_idx = lst[0][0]
        return first_idx
