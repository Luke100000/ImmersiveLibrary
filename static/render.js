const container = document.getElementById("render-container");
const body = document.getElementById("render-body");
const multiView = getSharedMultiView(false);

window.renderPreview = async ({project, content, width, height}) => {
    if (multiView.renderer.getContext().isContextLost()) {
        throw new Error("Render context was lost");
    }

    const disposePrevious = multiView.clear();
    body.replaceChildren();
    container.style.width = `${width}px`;
    container.style.height = `${height}px`;

    try {
        await embedContentPreview(body, project, content, {
            width,
            height,
            animate: false
        });
    } finally {
        // Keep shared shader programs alive until the next model is drawn.
        disposePrevious();
    }
};

const initial = document.getElementById("render-initial");
if (initial) {
    window.renderPreview(JSON.parse(initial.textContent)).catch((error) => {
        container.textContent = "Render error.";
        console.error(error);
    });
}
