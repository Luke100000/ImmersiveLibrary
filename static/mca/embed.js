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

            geometry.attributes.uv.array[face * 8] = x0;
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

function loadTexture(url) {
    let map = new THREE.TextureLoader().load(url);
    map.magFilter = THREE.NearestFilter;
    map.minFilter = THREE.NearestFilter;
    map.wrapS = THREE.ClampToEdgeWrapping;
    map.wrapT = THREE.ClampToEdgeWrapping;
    return map;
}

function setupScene(containerId, width, height) {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({alpha: true});
    renderer.setSize(width, height);
    document.getElementById(containerId).appendChild(renderer.domElement);
    return {scene, camera, renderer};
}

function createMaterials(skinUrl) {
    const clothingMaterial = new THREE.MeshBasicMaterial({alphaTest: 0.5, side: THREE.DoubleSide});
    const skinMaterial = new THREE.MeshBasicMaterial({map: loadTexture(skinUrl)});
    return {clothingMaterial, skinMaterial};
}

function addMeshes(scene, clothingMeshes, skinMeshes) {
    Object.values(clothingMeshes).forEach(mesh => scene.add(mesh));
    Object.values(skinMeshes).forEach(mesh => scene.add(mesh));
}

function animateMeshes(renderer, scene, camera, clothingMeshes, skinMeshes, animate) {
    let start;

    function update(timestamp) {
        if (start === undefined) {
            start = timestamp;
        }
        const time = timestamp - start;

        if (animate) {
            requestAnimationFrame(update);
        }

        const distance = 35;
        camera.rotation.y = 0.25;
        camera.position.x = Math.sin(camera.rotation.y) * distance;
        camera.position.y = -2;
        camera.position.z = Math.cos(camera.rotation.y) * distance;

        clothingMeshes["Head"].rotation.y = Math.cos(time * 0.001) * 0.5;
        clothingMeshes["Head"].rotation.x = Math.cos(time * 0.0007) * 0.2;
        clothingMeshes["Helm"].rotation.y = clothingMeshes["Head"].rotation.y;
        clothingMeshes["Helm"].rotation.x = clothingMeshes["Head"].rotation.x;
        skinMeshes["Head"].rotation.y = clothingMeshes["Head"].rotation.y;
        skinMeshes["Head"].rotation.x = clothingMeshes["Head"].rotation.x;

        function rotate(name, x, y, z) {
            ["", " Layer 2"].forEach(suffix => {
                if (clothingMeshes[name + suffix]) {
                    clothingMeshes[name + suffix].rotation.set(x, y, z);
                }
            });
            if (skinMeshes[name]) skinMeshes[name].rotation.set(x, y, z);
        }

        rotate("Left Arm", Math.cos(time * 0.0013) * 0.1, 0.01, 0.1);
        rotate("Right Arm", Math.cos(-time * 0.0013) * 0.1, -0.01, -0.1);
        rotate("Left Leg", -0.025, 0.01, 0);
        rotate("Right Leg", 0.025, -0.01, 0);

        renderer.render(scene, camera);
    }

    update();
}

// noinspection JSUnusedGlobalSymbols
export async function embed(containerId, data, width = 250, height = 400, animate = true) {
    const {scene, camera, renderer} = setupScene(containerId, width, height);
    const {clothingMaterial, skinMaterial} = createMaterials("/static/mca/skin.png");

    clothingMaterial.map = loadTexture('data:image/png;base64,' + data.content.data);
    clothingMaterial.needsUpdate = true;

    const clothingMeshes = getMeshes(clothingMaterial, 0.25, ["Head", "Helm", "Torso", "Torso Layer 2", "Right Arm", "Right Arm Layer 2", "Left Arm", "Left Arm Layer 2", "Right Leg", "Right Leg Layer 2", "Left Leg", "Left Leg Layer 2"]);
    const skinMeshes = getMeshes(skinMaterial, 0.0, ["Head", "Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]);

    addMeshes(scene, clothingMeshes, skinMeshes);
    animateMeshes(renderer, scene, camera, clothingMeshes, skinMeshes, animate);
}