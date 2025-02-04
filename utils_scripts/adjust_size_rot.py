import bpy
import math

def transform_active_bvh_armature():
    armature = bpy.context.active_object
    
    # Ensure the active object is indeed an armature
    if armature is None or armature.type != 'ARMATURE':
        print("Active object is not an armature. Please select the BVH armature first.")
        return
    
    # Rotate +90 degrees around X
    armature.rotation_euler[0] = math.radians(90.0)
    
    # Scale to (0.01, 0.01, 0.01)
    armature.scale = (0.01, 0.01, 0.01)
    
    # (Optional) Apply these transforms to bake them into the armature data
    # bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    print(f"Transformed armature '{armature.name}'")

# Run the function
transform_active_bvh_armature()
