if [ -z "$1" ]
  then
    echo "No argument supplied. Usage: ./make-dist v1.0"
    exit 1
fi

echo "preparing release $1"

addon_zip="Quick Arch $1 - Do not unzip!.zip"
zip -r "$addon_zip" qarch -x '*/.git/*' -x '*/.DS_Store' -x '*/.DS_Store/*' -x '*/__pycache__/*'
