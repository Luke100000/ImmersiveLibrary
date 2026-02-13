// noinspection JSCheckFunctionSignatures

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

function debugImage(atlasSize, atlas) {
    // Create a canvas to display the atlas
    const canvas = document.createElement('canvas');
    canvas.width = atlasSize;
    canvas.height = atlasSize;
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const imageData = new ImageData(
        new Uint8ClampedArray(atlas.buffer),
        atlasSize,
        atlasSize
    );
    ctx.putImageData(imageData, 0, 0);
}

function createSceneFromObject(data, containerId, width, height, animate) {
    const {Elements} = data.parsed.value;
    let elements = Elements.value.value;

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

    // Setup Three.js scene, camera, and renderer
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, width / height, 1.0, 16.0);
    const renderer = new THREE.WebGLRenderer({alpha: true, antialias: true});
    renderer.setSize(width, height);
    document.getElementById(containerId).appendChild(renderer.domElement);

    // Create a group to hold all elements
    const group = new THREE.Group();
    let minX = 0, minY = 0, minZ = 0;
    let maxX = 1, maxY = 1, maxZ = 1;
    elements.forEach((element, idx) => {
        const {From, To, Material, Type} = element;
        if (Type.value !== "element") return;

        const from = From.value.value;
        const to = To.value.value;

        // Calculate dimensions
        const width = Math.abs(to[0] - from[0]);
        const height = Math.abs(to[1] - from[1]);
        const depth = Math.abs(to[2] - from[2]);

        // Calculate position
        const x = (from[0] + to[0]) / 32 + ((idx * 23) % 7) * 0.0001;
        const y = (from[1] + to[1]) / 32 + ((idx * 23) % 13) * 0.0001;
        const z = (from[2] + to[2]) / 32 + ((idx * 23) % 17) * 0.0001;

        minX = Math.min(minX, x - width / 32);
        minY = Math.min(minY, y - height / 32);
        minZ = Math.min(minZ, z - depth / 32);
        maxX = Math.max(maxX, x + width / 32);
        maxY = Math.max(maxY, y + height / 32);
        maxZ = Math.max(maxZ, z + depth / 32);

        // Create material
        const material = new THREE.MeshStandardMaterial({
            map: texture,
            color: element.Color.value,
            transparent: !!(Material.value.Transparency && Material.value.Transparency.value !== "SOLID"),
            emissive: 0xffffff,
            emissiveIntensity: element.Emission ? element.Emission.value / 16.0 : 0.0,
        });

        // Create mesh
        const geometry = new THREE.BoxGeometry(width / 16.0, height / 16.0, depth / 16.0);
        const faces = ["east", "west", "up", "down", "south", "north"];
        faces.forEach((face, faceIndex) => {
            const key = `${idx}_${face}`;
            const region = regions[key];

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
        const cube = new THREE.Mesh(geometry, material);
        cube.position.set(x, y, z);

        // Apply rotation if specified
        const axis = element.Axis.value;
        const rotation = element.Rotation.value * (Math.PI / 180);
        if (axis === "x") cube.rotation.x = rotation;
        else if (axis === "y") cube.rotation.y = rotation;
        else if (axis === "z") cube.rotation.z = rotation;

        group.add(cube);
    });

    let centerX = (minX + maxX) / 2;
    let centerY = (minY + maxY) / 2;
    let centerZ = (minZ + maxZ) / 2;
    group.position.set(-centerX, -centerY, -centerZ);

    console.log(minX, maxX, minY, maxY, minZ, maxZ);

    const pivot = new THREE.Object3D();
    pivot.position.set(0, 0, 0);
    pivot.add(group);
    scene.add(pivot);

    // Position the camera
    const distance = 2.5;
    let sizeX = Math.max(Math.abs(maxX - centerX), Math.abs(minX - centerX));
    let sizeZ = Math.max(Math.abs(maxZ - centerZ), Math.abs(minZ - centerZ));
    camera.position.z = Math.sqrt(sizeX ** 2 + sizeZ ** 2) * distance;
    camera.position.y = camera.position.z * 0.25 * distance;
    camera.lookAt(0, 0, 0);

    // Add lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    // Animation loop
    let start;

    function update(timestamp) {
        if (start === undefined) {
            start = timestamp;
        }
        const time = timestamp - start;

        if (animate) {
            requestAnimationFrame(update);
        }

        pivot.rotation.y = Math.PI * 0.75 + time * 0.001;
        renderer.render(scene, camera);
    }

    update();

    // noinspection PointlessBooleanExpressionJS
    if (false) {
        // noinspection UnreachableCodeJS
        debugImage(atlasSize, atlas);
    }
}

// noinspection JSUnusedGlobalSymbols
export async function embed(containerId, content, width = 386, height = 386, animate = true) {
    const nbt = require('prismarine-nbt')
    const {Buffer} = require('buffer')

    const nbtBuffer = Buffer.from(atob(content.data), 'binary');
    nbt.parse(nbtBuffer).then(
        (parsedData) => {
            try {
                createSceneFromObject(parsedData, containerId, width, height, animate);
            } catch (e) {
                console.error("Error creating scene:", e);
                const container = document.getElementById(containerId);
                container.innerHTML = `<div class="error">Failed to render model: ${e.message}</div>`;
            }
        }
    );
}
