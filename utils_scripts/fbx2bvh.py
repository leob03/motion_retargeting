"""
This code is a variation of https://github.com/rubenvillegas/cvpr2018nkn/blob/master/datasets/fbx2bvh.py
"""
import os
import os.path as osp
from glob import glob

import bpy

print('start')
in_dir = '/home/innovation/dev-lbringer/blender_files/fbx_files/Crowd_mixamo/'
out_dir = osp.join(in_dir, 'fbx2bvh')
os.makedirs(out_dir, exist_ok=True)

fbx_files = glob(osp.join(in_dir, '*.fbx'))
for idx, in_file in enumerate(fbx_files):
    print(in_file)
    in_file_no_path = osp.split(in_file)[1]
    motion_name = osp.splitext(in_file_no_path)[0]
    out_file = osp.join(out_dir, f"{motion_name}.bvh")

    bpy.ops.import_scene.fbx(filepath=in_file)

    action = bpy.data.actions[-1]
    start_frame = int(action.frame_range[0])
    end_frame = int(action.frame_range[1])

    bpy.ops.export_anim.bvh(
        filepath=out_file,
        frame_start=start_frame,
        frame_end=end_frame,
        root_transform_only=True
    )
    bpy.data.actions.remove(bpy.data.actions[-1])

    print(f'{out_file} processed. #{idx + 1} of {len(fbx_files)}')
