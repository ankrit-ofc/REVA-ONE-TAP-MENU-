"""
Runs INSIDE Blender's bundled Python (invoked as `blender -b -P glb_to_usdz.py`).
Imports a GLB and exports a USDZ. Args after `--`: <input.glb> <output.usdz>.
"""

import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]

# Start from an empty scene so nothing from defaults leaks into the export.
bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.import_scene.gltf(filepath=src)

# Blender packages a .usdz (zipped USD + textures) when the filepath ends in .usdz.
bpy.ops.wm.usd_export(
    filepath=dst,
    export_textures=True,
    export_materials=True,
    selected_objects_only=False,
)
