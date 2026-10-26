async function embedContentPreview(contentElement, project, content, options = {}) {
    if (!contentElement) {
        throw new Error('Embed preview container not found');
    }
    const rect = contentElement.getBoundingClientRect();
    const width = options.width || Math.max(1, Math.floor(rect.width)) || 1;
    const height = options.height || (rect.height > 1 ? Math.floor(rect.height) : width);
    contentElement.style.height = `${height}px`;
    contentElement.style.minHeight = `${height}px`;
    contentElement.style.width = '100%';

    // Embed the project-specific content
    const {embed} = await import(`/static/${project}/embed.js`);
    const multiView = getSharedMultiView(options.animate ?? true);
    const view = await embed(contentElement, content, {...options, width, height});
    const unregister = view ? multiView.registerScene({...view, element: contentElement}) : undefined;

    if (options.animate === false) {
        multiView.render(0);
    }
    return unregister;
}

function createMultiViewRenderer(canvas, animate) {
    const renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setClearColor(0x000000, 0);

    let startTime;
    const views = new Set();

    function updateSize() {
        const isFullPage = canvas.parentElement === document.body || canvas.parentElement === document.documentElement;
        const width = isFullPage ? document.documentElement.clientWidth : canvas.clientWidth;
        const height = isFullPage ? document.documentElement.scrollHeight : canvas.clientHeight;
        const size = renderer.getSize(new THREE.Vector2());
        if (size.width !== width || size.height !== height) {
            if (isFullPage) {
                canvas.style.width = `${width}px`;
                canvas.style.height = `${height}px`;
            }
            renderer.setSize(width, height, false);
        }
    }

    function registerScene(view) {
        views.add(view);
        return () => views.delete(view);
    }

    // Detaches all views and returns a function that disposes their GPU resources.
    function clear() {
        const resources = new Set();

        for (const view of views) {
            view.scene.traverse((object) => {
                if (object.geometry) {
                    resources.add(object.geometry);
                }

                const objectMaterials = Array.isArray(object.material) ? object.material : [object.material];
                for (const material of objectMaterials) {
                    if (!material) continue;
                    resources.add(material);
                    for (const value of Object.values(material)) {
                        if (value && value.isTexture) {
                            resources.add(value);
                        }
                    }
                }
            });
        }

        views.clear();
        return () => {
            for (const resource of resources) {
                resource.dispose();
            }
            renderer.renderLists.dispose();
        };
    }

    function render(timestamp) {
        updateSize();

        renderer.setScissorTest(false);
        renderer.clear(true, true, true);
        renderer.setScissorTest(true);

        startTime ??= timestamp;
        const time = animate ? timestamp - startTime : 0;
        const canvasRect = canvas.getBoundingClientRect();

        for (const view of views) {
            if (!view.element.isConnected) {
                views.delete(view);
                continue;
            }

            const rect = view.element.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0
                || rect.bottom < canvasRect.top || rect.top > canvasRect.bottom
                || rect.right < canvasRect.left || rect.left > canvasRect.right) {
                continue;
            }

            const left = rect.left - canvasRect.left;
            const bottom = canvasRect.bottom - rect.bottom;
            renderer.setViewport(left, bottom, rect.width, rect.height);
            renderer.setScissor(left, bottom, rect.width, rect.height);

            if (view.camera.isPerspectiveCamera) {
                view.camera.aspect = rect.width / rect.height;
                view.camera.updateProjectionMatrix();
            }
            view.update?.(time, {width: rect.width, height: rect.height});

            renderer.render(view.scene, view.camera);
        }
    }

    if (animate) {
        renderer.setAnimationLoop(render);
    }

    return {renderer, registerScene, clear, render};
}

let sharedMultiView;

function getSharedMultiView(animate) {
    if (!sharedMultiView) {
        const canvas = document.getElementById('multiview-canvas');
        if (!canvas) {
            throw new Error('Expected canvas #multiview-canvas to exist');
        }
        sharedMultiView = createMultiViewRenderer(canvas, animate);
    }
    return sharedMultiView;
}
