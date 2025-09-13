export function loadTexture(url) {
    let map = new THREE.TextureLoader().load(url);
    map.magFilter = THREE.NearestFilter;
    map.minFilter = THREE.NearestFilter;
    map.wrapS = THREE.ClampToEdgeWrapping;
    map.wrapT = THREE.ClampToEdgeWrapping;
    return map;
}

export function setupScene(containerId, width = 200, height = 400) {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({alpha: true});
    renderer.setSize(width, height);
    document.getElementById(containerId).appendChild(renderer.domElement);
    return {scene, camera, renderer};
}

export function createMaterials(skinUrl) {
    const clothingMaterial = new THREE.MeshBasicMaterial({alphaTest: 0.5, side: THREE.DoubleSide});
    const skinMaterial = new THREE.MeshBasicMaterial({map: loadTexture(skinUrl)});
    return {clothingMaterial, skinMaterial};
}

export function addMeshes(scene, clothingMeshes, skinMeshes) {
    Object.values(clothingMeshes).forEach(mesh => scene.add(mesh));
    Object.values(skinMeshes).forEach(mesh => scene.add(mesh));
}

export function animateMeshes(renderer, scene, camera, clothingMeshes, skinMeshes) {
    const animate = function () {
        requestAnimationFrame(animate);
        const distance = 50;
        camera.rotation.y = 0.25;
        camera.position.x = Math.sin(camera.rotation.y) * distance;
        camera.position.z = Math.cos(camera.rotation.y) * distance;

        const time = Date.now();
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
    };
    animate();
}

// noinspection JSUnusedGlobalSymbols
export async function renderSkin(containerId, contentId, showTags = true) {
    const {scene, camera, renderer} = setupScene(containerId);
    const {clothingMaterial, skinMaterial} = createMaterials("/static/mca/skin.png");

    try {
        const res = await fetch(`/v1/content/mca/${contentId}`);
        const data = await res.json();

        clothingMaterial.map = loadTexture('data:image/png;base64,' + data.content.data);
        document.getElementById('title').innerText = data.content.title;
        document.getElementById('author').innerText = `by ${data.content.username}` + (data.content.likes ? `, ${data.content.likes} likes` : '');
        if (showTags && data.content.tags) {
            document.getElementById('tags').innerText = "Tags: " + data.content.tags.join(", ");
        }
        clothingMaterial.needsUpdate = true;

        const clothingMeshes = getMeshes(clothingMaterial, 0.25, ["Head", "Helm", "Torso", "Torso Layer 2", "Right Arm", "Right Arm Layer 2", "Left Arm", "Left Arm Layer 2", "Right Leg", "Right Leg Layer 2", "Left Leg", "Left Leg Layer 2"]);
        const skinMeshes = getMeshes(skinMaterial, 0.0, ["Head", "Torso", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]);

        addMeshes(scene, clothingMeshes, skinMeshes);
        animateMeshes(renderer, scene, camera, clothingMeshes, skinMeshes);

    } catch (err) {
        console.error('Error loading skin:', err);
    }
}
