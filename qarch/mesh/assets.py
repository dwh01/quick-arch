"""Importing mesh from other blend files"""
import bpy, bmesh

# use property update function
#  load file-> grab collection list and place into global enum generator
#              and put object names into dict[collection]=[names] for another enum generator
#  select collection enum -> push filter onto name picker enum function

# a smarter thing would be to register as an asset drop target and let user just dump assets from the asset library

# import mesh -> set layers and op id -> merge with active mesh
