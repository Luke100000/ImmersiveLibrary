const TEXTURE_ROOT = '/static/vendor/pixel-perfection/assets/minecraft/textures/';

// Animation frames last a number of game ticks
const TICK = 50;

const cache = new Map();

// Maps the sprite names of the elements to their textures, or to null for textures the pack does not have
export async function loadSprites(elements) {
    const ids = new Set(elements
        .filter(element => element.Type.value === 'sprite')
        .map(element => element.Sprite.value.Sprite.value));
    return new Map(await Promise.all([...ids].map(async id => [id, await loadSprite(id)])));
}

function loadSprite(id) {
    if (!cache.has(id)) cache.set(id, fetchSprite(id));
    return cache.get(id);
}

async function fetchSprite(id) {
    const [namespace, path] = id.split(':');
    if (namespace !== 'minecraft' || !/^(block|item)\/[a-z0-9_]+$/.test(path)) return null;

    const image = new Image();
    image.src = `${TEXTURE_ROOT}${path}.png`;
    try {
        await image.decode();
    } catch {
        return null;
    }

    // Animated textures are strips of frames, the texture shows one frame at a time
    const animation = image.naturalHeight > image.naturalWidth ? await fetchAnimation(path, image) : null;
    const canvas = document.createElement('canvas');
    canvas.width = animation?.width ?? image.naturalWidth;
    canvas.height = animation?.height ?? image.naturalWidth;
    canvas.getContext('2d').drawImage(image, 0, 0);

    const texture = new THREE.CanvasTexture(canvas);
    texture.magFilter = texture.minFilter = THREE.NearestFilter;
    texture.generateMipmaps = false;
    return {texture, ...measureTransparency(image), animation: animation && {...animation, image, canvas}};
}

// Judged over all frames
function measureTransparency(image) {
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d', {willReadFrequently: true});
    context.drawImage(image, 0, 0);

    let cutout = false;
    let translucent = false;
    const {data} = context.getImageData(0, 0, canvas.width, canvas.height);
    for (let i = 3; i < data.length; i += 4) {
        if (data[i] === 0) cutout = true;
        else if (data[i] < 255) translucent = true;
    }
    return {cutout, translucent};
}

async function fetchAnimation(path, image) {
    const response = await fetch(`${TEXTURE_ROOT}${path}.png.mcmeta`);
    const meta = response.ok ? (await response.json().catch(() => ({}))).animation ?? {} : {};

    const width = meta.width ?? image.naturalWidth;
    const height = meta.height ?? width;
    const frametime = meta.frametime ?? 1;
    const indices = meta.frames ?? Array.from({length: Math.floor(image.naturalHeight / height)}, (_, i) => i);
    const sequence = indices.map(frame => typeof frame === 'number'
        ? {index: frame, time: frametime}
        : {index: frame.index, time: frame.time ?? frametime});
    const duration = sequence.reduce((sum, frame) => sum + frame.time, 0);
    return duration > 0 ? {width, height, sequence, duration, interpolate: !!meta.interpolate} : null;
}

export function animateSprite({texture, animation}, time) {
    if (!animation) return;

    // Find the frame the time falls into, ticks ends up as the progress within it
    let ticks = (time / TICK) % animation.duration;
    let current = 0;
    while (ticks >= animation.sequence[current].time) ticks -= animation.sequence[current++].time;

    const {index, time: length} = animation.sequence[current];
    const next = animation.sequence[(current + 1) % animation.sequence.length].index;
    const blend = animation.interpolate ? ticks / length : 0;

    const shown = `${index}:${next}:${blend}`;
    if (shown === animation.shown) return;
    animation.shown = shown;

    const {image, canvas, width, height} = animation;
    const context = canvas.getContext('2d');
    context.clearRect(0, 0, width, height);
    context.globalAlpha = 1;
    context.drawImage(image, 0, index * height, width, height, 0, 0, width, height);
    if (blend) {
        context.globalAlpha = blend;
        context.drawImage(image, 0, next * height, width, height, 0, 0, width, height);
    }
    texture.needsUpdate = true;
}

// Sprites are flat and show their texture unmirrored from the north. Tiled ones repeat from the top left.
export function createSprite(element, material) {
    const {Rotation, Size, Tiled} = element.Sprite.value;
    const from = element.From.value.value;
    const to = element.To.value.value;
    const width = Math.trunc(Math.abs(to[0] - from[0]));
    const height = Math.trunc(Math.abs(to[1] - from[1]));

    // One texture covers 16 * size pixels
    const scale = 16 * (Size?.value ?? 1);
    const stepX = Tiled?.value ? Math.max(1, Math.round(scale)) : width;
    const stepY = Tiled?.value ? Math.max(1, Math.round(scale)) : height;
    const shift = Math.round((Rotation?.value ?? 0) / 90) & 3;

    const tiles = new THREE.Group();
    // Uploads are untrusted, this stops absurd tilings
    if (Math.ceil(width / stepX) * Math.ceil(height / stepY) > 1024) return tiles;

    for (let x = 0; x < width; x += stepX) {
        for (let y = 0; y < height; y += stepY) {
            const w = Math.min(width - x, stepX);
            const h = Math.min(height - y, stepY);
            const geometry = new THREE.PlaneGeometry(w / 16, h / 16).rotateY(Math.PI);

            // Partial tiles show the top left of the texture. Corners run top left, bottom left, bottom right, top right
            const fx = Math.min(1, w / scale);
            const fy = Math.min(1, h / scale);
            const corners = [[0, 1], [0, 1 - fy], [fx, 1 - fy], [fx, 1]];
            [0, 3, 1, 2].forEach((corner, vertex) => {
                geometry.attributes.uv.setXY(vertex, ...corners[(corner + shift) % 4]);
            });

            const tile = new THREE.Mesh(geometry, material);
            tile.position.set((x + w / 2 - width / 2) / 16, -(y + h / 2 - height / 2) / 16, 0);
            tiles.add(tile);
        }
    }
    return tiles;
}
