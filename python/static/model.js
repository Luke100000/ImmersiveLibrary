const uvs = {
    "Head": [
        [8, 0, 16, 8],
        [16, 0, 24, 8],
        [0, 8, 8, 16],
        [8, 8, 16, 16],
        [16, 8, 24, 16],
        [24, 8, 32, 16]
    ],
    "Helm": [
        [40, 0, 48, 8],
        [48, 0, 56, 8],
        [32, 8, 40, 16],
        [40, 8, 48, 16],
        [48, 8, 56, 16],
        [56, 8, 64, 16]
    ],
    "Torso": [
        [20, 16, 28, 20],
        [28, 16, 36, 20],
        [16, 20, 20, 32],
        [20, 20, 28, 32],
        [28, 20, 32, 32],
        [32, 20, 40, 32]
    ],
    "Torso Layer 2": [
        [20, 48, 28, 36],
        [28, 48, 36, 36],
        [16, 36, 20, 48],
        [20, 36, 28, 48],
        [28, 36, 32, 48],
        [32, 36, 40, 48]
    ],
    "Left Arm": [
        [36, 48, 40, 52],
        [40, 48, 44, 52],
        [32, 52, 36, 64],
        [36, 52, 40, 64],
        [40, 52, 44, 64],
        [44, 52, 48, 64]
    ],
    "Left Arm Layer 2": [
        [52, 48, 56, 52],
        [56, 48, 60, 52],
        [48, 52, 52, 64],
        [52, 52, 56, 64],
        [56, 52, 60, 64],
        [60, 52, 64, 64]
    ],
    "Right Arm": [
        [44, 16, 48, 20],
        [48, 16, 52, 20],
        [40, 20, 44, 32],
        [44, 20, 48, 32],
        [48, 20, 52, 32],
        [52, 20, 56, 32]
    ],
    "Right Arm Layer 2": [
        [44, 48, 48, 36],
        [48, 48, 52, 36],
        [40, 36, 44, 48],
        [44, 36, 48, 48],
        [48, 36, 52, 48],
        [52, 36, 64, 48]
    ],
    "Left Leg": [
        [20, 48, 24, 52],
        [24, 48, 28, 52],
        [16, 52, 20, 64],
        [20, 52, 24, 64],
        [24, 52, 28, 64],
        [28, 52, 32, 64]
    ],
    "Left Leg Layer 2": [
        [4, 48, 8, 52],
        [8, 48, 12, 52],
        [0, 52, 4, 64],
        [4, 52, 8, 64],
        [8, 52, 12, 64],
        [12, 52, 16, 64]
    ],
    "Right Leg": [
        [4, 16, 8, 20],
        [8, 16, 12, 20],
        [0, 20, 4, 32],
        [4, 20, 8, 32],
        [8, 20, 12, 32],
        [12, 20, 16, 32]
    ],
    "Right Leg Layer 2": [
        [4, 48, 8, 36],
        [8, 48, 12, 36],
        [0, 36, 4, 48],
        [4, 36, 8, 48],
        [8, 36, 12, 48],
        [12, 36, 16, 48]
    ],
}

const offsets = {
    "Head": [0, 10, 0],
    "Helm": [0, 10, 0],
    "Torso": [0, 0, 0],
    "Torso Layer 2": [0, 0, 0],
    "Left Arm": [6.5, 0, 0],
    "Left Arm Layer 2": [6.5, 0, 0],
    "Right Arm": [-6.5, 0, 0],
    "Right Arm Layer 2": [-6.5, 0, 0],
    "Left Leg": [2, -12, 0.25],
    "Left Leg Layer 2": [2, -12, 0.25],
    "Right Leg": [-2, -12, -0.25],
    "Right Leg Layer 2": [-2, -12, -0.25],
}

let dilate = 0.5;
const sizes = {
    "Head": [8, 8, 8],
    "Helm": [8 + dilate, 8 + dilate, 8 + dilate],
    "Torso": [8, 12, 4],
    "Torso Layer 2": [8 + dilate, 12 + dilate, 4 + dilate],
    "Left Arm": [4, 12, 4],
    "Left Arm Layer 2": [4 + dilate, 12 + dilate, 4 + dilate],
    "Right Arm": [4, 12, 4],
    "Right Arm Layer 2": [4 + dilate, 12 + dilate, 4 + dilate],
    "Left Leg": [4, 12, 4],
    "Left Leg Layer 2": [4 + dilate, 12 + dilate, 4 + dilate],
    "Right Leg": [4, 12, 4],
    "Right Leg Layer 2": [4 + dilate, 12 + dilate, 4 + dilate],
}

function getMeshes(material, dilate, keys) {
    let meshes = {};

    // Create a mesh for each body part
    for (const i in keys) {
        const key = keys[i];
        const uv = uvs[key];
        let geometry = new THREE.BoxGeometry(sizes[key][0] + dilate, sizes[key][1] + dilate, sizes[key][2] + dilate);

        const faceMapping = [4, 2, 0, 1, 3, 5];
        const antiBleed = 0.01 / 64.0;

        for (let face = 0; face < 6; face++) {
            const mappedFace = faceMapping[face];
            const x0 = uv[mappedFace][0] / 64 + antiBleed;
            const y0 = 1 - uv[mappedFace][1] / 64 - antiBleed;
            const x1 = uv[mappedFace][2] / 64 - antiBleed;
            const y1 = 1 - uv[mappedFace][3] / 64 + antiBleed;

            geometry.attributes.uv.array[face * 8 + 0] = x0;
            geometry.attributes.uv.array[face * 8 + 1] = y0;
            geometry.attributes.uv.array[face * 8 + 2] = x1;
            geometry.attributes.uv.array[face * 8 + 3] = y0;
            geometry.attributes.uv.array[face * 8 + 4] = x0;
            geometry.attributes.uv.array[face * 8 + 5] = y1;
            geometry.attributes.uv.array[face * 8 + 6] = x1;
            geometry.attributes.uv.array[face * 8 + 7] = y1;
        }

        const mesh = new THREE.Mesh(geometry, material);

        // Set the position of the mesh
        mesh.position.x = offsets[key][0];
        mesh.position.y = offsets[key][1];
        mesh.position.z = offsets[key][2];

        // Add the mesh to the list of meshes
        meshes[key] = mesh;
    }

    return meshes;
}