// noinspection JSCheckFunctionSignatures

import {animateSprite, createSprite, loadSprites} from './sprites.js';

// The average color of oak planks
const FALLBACK_COLOR = 0xa2824e;

function intArrayToRGBA(pixelsInt, width, height) {
    const pixelsRGBA = new Uint8Array(width * height * 4);
    for (let i = 0; i < pixelsInt.length; i++) {
        const rgba = intToRGBA(pixelsInt[i]);
        pixelsRGBA[i * 4] = rgba.r;
        pixelsRGBA[i * 4 + 1] = rgba.g;
        pixelsRGBA[i * 4 + 2] = rgba.b;
        pixelsRGBA[i * 4 + 3] = rgba.a;
    }
    return pixelsRGBA;
}

function intToRGBA(int) {
    return {
        a: (int >> 24) & 0xFF,
        b: (int >> 16) & 0xFF,
        g: (int >> 8) & 0xFF,
        r: int & 0xFF,
    };
}

class QuadtreePacker {
    constructor(maxSize = 512) {
        this.maxSize = maxSize;
        this.size = 64;
        this.atlas = null;
        this.regions = {};
    }

    pack(textures) {
        while (this.size <= this.maxSize) {
            this.atlas = new Uint8Array(this.size * this.size * 4);
            this.regions = {};
            let quads = [{x: 0, y: 0, w: this.size, h: this.size}];
            if (this.tryPack(textures, quads)) {
                return {atlas: this.atlas, regions: this.regions, size: this.size};
            }
            this.size *= 2;
        }
        throw new Error("Textures too large to pack");
    }

    tryPack(textures, quads) {
        for (const [name, texture] of Object.entries(textures)) {
            const {width, height, pixels} = texture;
            const bestQuad = this.findBestQuad(quads, width, height);
            if (!bestQuad) {
                return false;
            }
            this.regions[name] = {x: bestQuad.x, y: bestQuad.y, width, height};
            this.placeTexture(pixels, bestQuad.x, bestQuad.y, width, height);
            quads = this.splitQuad(quads, bestQuad, width, height);
        }
        return true;
    }

    findBestQuad(quads, textureW, textureH) {
        return quads.reduce((best, quad) => {
            if (quad.w < textureW || quad.h < textureH) return best;

            const quadSize = quad.w * quad.h;
            const textureSize = textureW * textureH;
            const loss = (quadSize - textureSize) / quadSize;

            return (!best || loss < best.loss) ? {quad, loss} : best;
        }, null)?.quad;
    }

    splitQuad(quads, usedQuad, textureW, textureH) {
        const newQuads = [];
        const {x, y, w, h} = usedQuad;
        const remainingW = w - textureW;
        const remainingH = h - textureH;

        if (remainingW > 0 && remainingH > 0) {
            if (remainingW > remainingH) {
                newQuads.push({x: x + textureW, y, w: remainingW, h: h});
                newQuads.push({x: x, y: y + textureH, w: textureW, h: remainingH});
            } else {
                newQuads.push({x: x + textureW, y, w: remainingW, h: textureH});
                newQuads.push({x, y: y + textureH, w: w, h: remainingH});
            }
        } else if (remainingW > 0) {
            newQuads.push({x: x + textureW, y, w: remainingW, h: h});
        } else if (remainingH > 0) {
            newQuads.push({x, y: y + textureH, w: w, h: remainingH});
        }

        return [...quads.filter(q => q !== usedQuad), ...newQuads];
    }

    placeTexture(pixels, x, y, width, height) {
        for (let i = 0; i < height; i++) {
            for (let j = 0; j < width; j++) {
                const srcIdx = (i * width + j) * 4;
                const dstIdx = ((y + i) * this.size + (x + j)) * 4;
                this.atlas[dstIdx] = pixels[srcIdx];
                this.atlas[dstIdx + 1] = pixels[srcIdx + 1];
                this.atlas[dstIdx + 2] = pixels[srcIdx + 2];
                this.atlas[dstIdx + 3] = pixels[srcIdx + 3];
            }
        }
    }
}

function createUVMapping(region, atlasSize) {
    const margin = 0.5 / atlasSize;
    const {x, y, width, height} = region;
    const u = x / atlasSize + margin;
    const v = y / atlasSize + margin;
    const u2 = (x + width) / atlasSize - margin;
    const v2 = (y + height) / atlasSize - margin;
    return [u, v2, u2, v];
}

function listTextures(elements) {
    const textures = {};
    elements.forEach((element, idx) => {
        const {From, To, BakedTexture} = element;
        if (BakedTexture) {
            Object.entries(BakedTexture.value).forEach(([face, textureData]) => {
                const key = `${idx}_${face}`;

                const from = From.value.value;
                const to = To.value.value;
                const width = Math.abs(to[0] - from[0]);
                const height = Math.abs(to[1] - from[1]);
                const depth = Math.abs(to[2] - from[2]);

                let textureWidth, textureHeight;
                if (face === 'east' || face === 'west') {
                    textureWidth = depth;
                    textureHeight = height;
                } else if (face === 'up' || face === 'down') {
                    textureWidth = width;
                    textureHeight = depth;
                } else {
                    textureWidth = width;
                    textureHeight = height;
                }

                textures[key] = {
                    width: textureWidth,
                    height: textureHeight,
                    pixels: intArrayToRGBA(textureData.value, textureWidth, textureHeight),
                };
            });
        }
    });
    return textures;
}

// Deterministic pseudo-random value in [-1, 1) for an integer seed
function hashToUnit(seed) {
    let h = Math.imul(seed ^ (seed >>> 16), 0x45d9f3b);
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b);
    return ((h ^ (h >>> 16)) >>> 0) / 0x80000000 - 1;
}

function createMaterial(element, properties) {
    return new THREE.MeshStandardMaterial({
        color: element.Color.value,
        emissive: 0xffffff,
        emissiveIntensity: element.Emission ? element.Emission.value / 16.0 : 0.0,
        ...properties,
    });
}

// Offsets each element slightly so coplanar faces of different elements do not z-fight
function placeElement(object, element, idx) {
    const jitter = 0.0003;
    const from = element.From.value.value;
    const to = element.To.value.value;
    object.position.set(
        (from[0] + to[0]) / 32 + hashToUnit(idx * 3) * jitter,
        (from[1] + to[1]) / 32 + hashToUnit(idx * 3 + 1) * jitter,
        (from[2] + to[2]) / 32 + hashToUnit(idx * 3 + 2) * jitter,
    );
    object.rotation[element.Axis.value] = element.Rotation.value * (Math.PI / 180);
    return object;
}

function isBaked(element) {
    return Object.keys(element.BakedTexture?.value ?? {}).length > 0;
}

function createCube(element, idx, texture, regions, atlasSize, unbaked) {
    const from = element.From.value.value;
    const to = element.To.value.value;
    const width = Math.abs(to[0] - from[0]);
    const height = Math.abs(to[1] - from[1]);
    const depth = Math.abs(to[2] - from[2]);

    const transparency = element.Material.value.Transparency;
    const transparent = !!(transparency && transparency.value !== "SOLID");

    // Some uploads lack all baked textures, the game shows those elements as oak
    if (unbaked) {
        const material = createMaterial(element, {transparent});
        material.color.multiply(new THREE.Color(FALLBACK_COLOR));
        return new THREE.Mesh(new THREE.BoxGeometry(width / 16.0, height / 16.0, depth / 16.0), material);
    }

    const material = createMaterial(element, {map: texture, transparent});

    const geometry = new THREE.BoxGeometry(width / 16.0, height / 16.0, depth / 16.0);
    const faces = ["east", "west", "up", "down", "south", "north"];
    faces.forEach((face, faceIndex) => {
        const region = regions[`${idx}_${face}`];

        const i = faceIndex * 4;
        if (region) {
            const [u, v, u2, v2] = createUVMapping(region, atlasSize);
            const uv = geometry.attributes.uv;
            uv.setXY(i, u, v2);
            uv.setXY(i + 1, u2, v2);
            uv.setXY(i + 2, u, v);
            uv.setXY(i + 3, u2, v);
        } else {
            const pos = geometry.attributes.position;
            pos.setXYZ(i, 0, 0, 0);
            pos.setXYZ(i + 1, 0, 0, 0);
            pos.setXYZ(i + 2, 0, 0, 0);
            pos.setXYZ(i + 3, 0, 0, 0);
        }
    });
    return new THREE.Mesh(geometry, material);
}

// The camera looks down at the model, which turns around the y axis from the start angle
const ELEVATION = Math.atan(0.625);
const START_ANGLE = Math.PI * 0.75;

// Small models are framed as if they were half a block in size
const MIN_HALF_SIZE = 0.25;

// The distance at which a turning model fits the view at any angle
function turningFitDistance(camera, halfSize) {
    const radius = Math.max(Math.hypot(halfSize.x, halfSize.z), MIN_HALF_SIZE);
    const halfHeight = Math.max(halfSize.y, MIN_HALF_SIZE);
    const tanY = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const tanX = tanY * camera.aspect;
    const projectedHeight = halfHeight * Math.cos(ELEVATION) + radius * Math.sin(ELEVATION);
    return radius + Math.max(projectedHeight / tanY, radius / tanX);
}

// A point as [right, up, toward the camera] seen from the camera's direction
function toView({x, y, z}) {
    const sin = Math.sin(ELEVATION);
    const cos = Math.cos(ELEVATION);
    return [x, y * cos - z * sin, y * sin + z * cos];
}

// The model's vertices and the corners of the minimum size, in view space
function viewPoints(model) {
    model.updateMatrixWorld(true);
    const points = [];
    const vertex = new THREE.Vector3();
    model.traverse((mesh) => {
        if (!mesh.isMesh) return;
        const positions = mesh.geometry.attributes.position;
        for (let i = 0; i < positions.count; i++) {
            points.push(toView(vertex.fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld)));
        }
    });
    for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
        points.push(toView(vertex.set(x, y, z).multiplyScalar(MIN_HALF_SIZE)));
    }
    return points;
}

// The distance and screen center that fill the view with a still model.
// It stays within the view's central square, which previews are cropped to.
function stillFit(camera, model) {
    const margin = 0.95;
    const tanY = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * margin;
    const tanX = tanY * Math.min(camera.aspect, 1);
    const points = viewPoints(model);

    // Each pass fits the model around the previous pass's center, which settles within a few passes
    let center = [0, 0];
    let distance;
    for (let pass = 0; pass < 4; pass++) {
        const [centerX, centerY] = center;
        distance = 0;
        for (const [x, y, z] of points) {
            distance = Math.max(distance, z + Math.max(
                x / (tanX + centerX), -x / (tanX - centerX),
                y / (tanY + centerY), -y / (tanY - centerY),
            ));
        }

        let [left, right, bottom, top] = [Infinity, -Infinity, Infinity, -Infinity];
        for (const [x, y, z] of points) {
            left = Math.min(left, x / (distance - z));
            right = Math.max(right, x / (distance - z));
            bottom = Math.min(bottom, y / (distance - z));
            top = Math.max(top, y / (distance - z));
        }
        center = [(left + right) / 2, (bottom + top) / 2];
    }
    return {distance, center};
}

function placeCamera(camera, distance, sphereRadius) {
    camera.position.set(0, distance * Math.sin(ELEVATION), distance * Math.cos(ELEVATION));
    camera.lookAt(0, 0, 0);

    // Tight clipping planes keep the depth buffer precise
    camera.near = Math.max(distance - sphereRadius, 0.05);
    camera.far = distance + sphereRadius;
    camera.updateProjectionMatrix();
}

// Shifts the view so the given screen center, in tangent units, is in its middle
function centerView(camera, [x, y]) {
    const tanY = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    camera.setViewOffset(camera.aspect, 1, x / (2 * tanY), -y / (2 * tanY), camera.aspect, 1);
}

function createSceneFromObject(data, options = {}, sprites = new Map()) {
    const {Elements} = data.parsed.value;
    const elements = Elements.value.value;

    // Single unbaked elements are hidden in this state, e.g., fully enclosed by others
    const unbaked = !elements.some((element) => element.Type.value === "element" && isBaked(element));

    // Collect all textures from elements
    const textures = listTextures(elements);

    // Pack textures into atlas
    const packer = new QuadtreePacker();
    const {atlas, regions, size: atlasSize} = packer.pack(textures);

    // Create Three.js texture from atlas
    const texture = new THREE.DataTexture(
        atlas,
        atlasSize,
        atlasSize,
        THREE.RGBAFormat
    );
    texture.needsUpdate = true;

    // Setup Three.js scene and camera
    const scene = new THREE.Scene();
    // A narrow lens keeps the edges of still renders close to parallel
    const fov = options.animate === false ? 30 : 50;
    const camera = new THREE.PerspectiveCamera(fov, options.width / options.height, 0.1, 16.0);

    // Create a group to hold all elements
    const group = new THREE.Group();
    elements.forEach((element, idx) => {
        const type = element.Type.value;
        if (type === "element") {
            group.add(placeElement(createCube(element, idx, texture, regions, atlasSize, unbaked), element, idx));
        } else if (type === "sprite") {
            const sprite = sprites.get(element.Sprite.value.Sprite.value);
            if (!sprite) return;

            const material = createMaterial(element, {
                map: sprite.texture,
                side: THREE.DoubleSide,
                transparent: sprite.translucent,
                alphaTest: sprite.cutout ? 0.5 : 0,
            });
            group.add(placeElement(createSprite(element, material), element, idx));
        }
    });

    const bounds = new THREE.Box3().setFromObject(group, true);
    if (bounds.isEmpty()) bounds.set(new THREE.Vector3(), new THREE.Vector3(1, 1, 1));
    const center = bounds.getCenter(new THREE.Vector3());
    group.position.copy(center).negate();

    const pivot = new THREE.Object3D();
    pivot.rotation.y = START_ANGLE;
    pivot.add(group);
    scene.add(pivot);

    const halfSize = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
    const sphereRadius = Math.max(halfSize.length(), MIN_HALF_SIZE);
    if (options.animate === false) {
        const {distance, center} = stillFit(camera, pivot);
        placeCamera(camera, distance, sphereRadius);
        centerView(camera, center);
    } else {
        placeCamera(camera, turningFitDistance(camera, halfSize), sphereRadius);
    }

    // Add lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    const update = function update(time) {
        pivot.rotation.y = START_ANGLE + time * 0.0005;
        sprites.forEach(sprite => sprite && animateSprite(sprite, time));
    }

    return {scene, camera, update};
}

let nbtLibrary;

// The NBT parser is large and only needed here, so it is loaded on first use. It defines a global require.
function loadNbtLibrary() {
    nbtLibrary ??= new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/static/vendor/pnbt.js';
        script.onload = () => resolve(window.require);
        script.onerror = () => reject(new Error('Unable to load the NBT parser'));
        document.head.append(script);
    });
    return nbtLibrary;
}

// noinspection JSUnusedGlobalSymbols
export async function embed(element, content, options = {}) {
    const load = await loadNbtLibrary();
    const nbt = load('prismarine-nbt');
    const {Buffer} = load('buffer');

    const parsedData = await nbt.parse(Buffer.from(atob(content.data), 'binary'));
    const sprites = await loadSprites(parsedData.parsed.value.Elements.value.value);
    return createSceneFromObject(parsedData, options, sprites);
}
