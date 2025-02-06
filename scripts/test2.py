import bpy
import os
import gc

# Configuration
bvh_source_dir = "/home/innovation/dev-lbringer/retargeting/motion_retargeting/source_motion"
fbx_output_dir = "/home/innovation/dev-lbringer/retargeting/motion_retargeting/target_motion"
fbx_model_path = "/home/innovation/dev-lbringer/retargeting/motion_retargeting/fbx_files/Mixamo_Mannequin.fbx"

def clean_scene():
    """Remove all objects and clear orphan data"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    # Purge unused data blocks
    for block in [bpy.data.meshes, bpy.data.materials, bpy.data.armatures]:
        for item in block:
            block.remove(item)
    gc.collect()

def retarget_bvh_to_fbx(bvh_path, fbx_output_path):
    """Core retargeting function"""
    clean_scene()
    
    # 1. Import FBX Character (Target Armature)
    bpy.ops.import_scene.fbx(filepath=fbx_model_path)
    fbx_armature = next((obj for obj in bpy.context.selected_objects if obj.type == 'ARMATURE'), None)
    
    if not fbx_armature:
        raise RuntimeError("FBX armature failed to import")
    
    # Set FBX scale (Mixamo characters often need scaling down)
    fbx_armature.scale = (0.1, 0.1, 0.1)
    bpy.context.view_layer.update()
    
    # 2. Import BVH Motion (Source Armature)
    bpy.ops.import_anim.bvh(filepath=bvh_path)
    bvh_armature = next((obj for obj in bpy.context.selected_objects if obj.type == 'ARMATURE'), None)
    
    if not bvh_armature:
        raise RuntimeError("BVH armature failed to import")
    
    # 3. Configure Auto-Rig Pro Retargeting
    bpy.context.scene.source_rig = bvh_armature.name
    bpy.context.scene.target_rig = fbx_armature.name
    
    # Critical ARP steps
    bpy.ops.arp.auto_scale()  # Match bone lengths
    bpy.ops.arp.build_bones_list()  # Auto-detect bone chains
    bpy.ops.arp.import_config_preset(preset_name='bvh_to_fbx_mapping')  # Your bone mapping preset
    bpy.ops.arp.retarget()  # Transfer animation
    
    # 4. Export Animated FBX
    bpy.ops.object.select_all(action='DESELECT')
    fbx_armature.select_set(True)
    for child in fbx_armature.children:
        child.select_set(True)
    
    bpy.ops.export_scene.fbx(
        filepath=fbx_output_path,
        use_selection=True,
        bake_anim=True,
        bake_anim_use_all_bones=True,
        add_leaf_bones=False,
        axis_forward='-Z',
        axis_up='Y',
        global_scale=1.0  # Already scaled during import
    )

if __name__ == '__main__':
    # Create output directory
    os.makedirs(fbx_output_dir, exist_ok=True)
    
    # Process all BVH files
    for bvh_file in os.listdir(bvh_source_dir):
        if not bvh_file.endswith(".bvh"):
            continue
            
        bvh_path = os.path.join(bvh_source_dir, bvh_file)
        fbx_output_path = os.path.join(fbx_output_dir, f"{os.path.splitext(bvh_file)[0]}.fbx")
        
        print(f"Processing: {bvh_file} -> {fbx_output_path}")
        try:
            retarget_bvh_to_fbx(bvh_path, fbx_output_path)
        except Exception as e:
            print(f"Failed to process {bvh_file}: {str(e)}")