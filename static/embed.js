// noinspection JSUnusedGlobalSymbols
async function embedContent(containerId, project, content) {
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

    // Embed the project-specific content
    const {embed} = await import(`/static/${project}/embed.js`);
    embed(`${containerId}-content`, content);
}

window.embedContent = embedContent;