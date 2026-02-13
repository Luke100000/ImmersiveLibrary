// noinspection JSUnusedGlobalSymbols
async function embedContent(containerId, project, content, options = {}) {
    if (typeof content === 'number') {
        const res = await fetch(`/v1/content/${project}/${content}`);
        content = (await res.json()).content;
    }

    // General layout
    const parentDiv = document.getElementById(containerId);
    parentDiv.innerHTML = `
        <div class="title" id="${containerId}-title">${content.title}</div>
        <div class="author" id="${containerId}-author">${content.username}</div>
        <div class="content" id="${containerId}-content"></div>
        <div class="tags-container" id="${containerId}-tags"></div>
    `;

    // Tags
    const tagsContainer = document.getElementById(`${containerId}-tags`);
    if (tagsContainer && content.tags && content.tags.length > 0) {
        content.tags.forEach(tag => {
            const tagSpan = document.createElement('span');
            tagSpan.textContent = tag;
            tagSpan.className = 'tag';
            tagsContainer.appendChild(tagSpan);
        });
    }

    await embedContentPreview(`${containerId}-content`, project, content, options)
}

async function embedContentPreview(containerId, project, content, options = {}) {
    const contentElement = document.getElementById(containerId);
    const rect = contentElement.getBoundingClientRect();
    const resolvedWidth = options.width || Math.max(1, Math.floor(rect.width || contentElement.clientWidth)) || 1;
    const measuredHeight = rect.height || contentElement.clientHeight;
    const resolvedHeight = options.height || (measuredHeight > 1 ? Math.floor(measuredHeight) : resolvedWidth);
    contentElement.style.height = `${resolvedHeight}px`;
    contentElement.style.minHeight = `${resolvedHeight}px`;
    contentElement.style.width = '100%';

    // Embed the project-specific content
    const {embed} = await import(`/static/${project}/embed.js`);
    const multiView = getSharedMultiView(options.animate ?? true);
    const embedOptions = {
        ...options,
        width: resolvedWidth,
        height: resolvedHeight,
        element: contentElement,
        multiView,
    };
    const view = await embed(contentElement, content, embedOptions);
    if (view) {
        multiView.registerScene({
            scene: view.scene,
            camera: view.camera,
            element: contentElement,
            update: view.update,
        });
    }
}

function createMultiViewRenderer(canvas, animate) {
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setClearColor(0x000000, 0);

    let startTime;
    const views = new Set();

    function updateSize() {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        const size = renderer.getSize(new THREE.Vector2());
        if (size.width !== width || size.height !== height) {
            renderer.setSize(width, height, false);
            console.log("Updated renderer size to", width, height);
        }
    }

    function registerScene(view) {
        if (!view || !view.scene || !view.camera || !view.element) return null;
        views.add(view);
        return () => views.delete(view);
    }

    function clear() {
        views.clear();
    }

    function render(timestamp) {
        updateSize();
        canvas.style.transform = 'none';

        renderer.setScissorTest(false);
        renderer.clear(true, true, true);
        renderer.setScissorTest(true);

        const canvasRect = canvas.getBoundingClientRect();
        const viewportHeight = canvasRect.height;
        const viewportWidth = canvasRect.width;

        Array.from(views).forEach((view) => {
            if (!view.element || !view.element.isConnected) {
                views.delete(view);
                return;
            }

            const rect = view.element.getBoundingClientRect();
            if (rect.bottom < canvasRect.top || rect.top > canvasRect.bottom || rect.right < canvasRect.left || rect.left > canvasRect.right) {
                return;
            }

            const width = rect.right - rect.left;
            const height = rect.bottom - rect.top;
            if (width <= 0 || height <= 0) return;

            const left = rect.left - canvasRect.left;
            const bottom = canvasRect.bottom - rect.bottom;

            if (left > viewportWidth || bottom > viewportHeight || left + width < 0 || bottom + height < 0) {
                return;
            }

            renderer.setViewport(left, bottom, width, height);
            renderer.setScissor(left, bottom, width, height);

            if (view.camera && view.camera.isPerspectiveCamera) {
                view.camera.aspect = width / height;
                view.camera.updateProjectionMatrix();
            }

            if (typeof view.update === 'function') {
                if (startTime === undefined) {
                    startTime = timestamp;
                }
                const time = animate ? (timestamp - startTime) : 0;
                view.update(time, {width, height});
            }

            renderer.render(view.scene, view.camera);
        });
    }

    function start() {
        renderer.setAnimationLoop(render);
    }

    function stop() {
        renderer.setAnimationLoop(null);
    }

    return {renderer, registerScene, clear, start, stop};
}

function getSharedMultiView(animate) {
    const canvasId = 'multiview-canvas';
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        throw new Error(`Expected canvas #${canvasId} to exist`);
    }

    window.ImmersiveMultiView = window.ImmersiveMultiView || {};
    if (!window.ImmersiveMultiView.shared) {
        const multiView = createMultiViewRenderer(canvas, animate);
        multiView.start();
        window.ImmersiveMultiView.shared = multiView;
    }

    return window.ImmersiveMultiView.shared;
}

window.embedContent = embedContent;
window.ImmersiveMultiView = window.ImmersiveMultiView || {};
window.ImmersiveMultiView.createRenderer = createMultiViewRenderer;
