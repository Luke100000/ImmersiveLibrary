// noinspection JSUnusedGlobalSymbols
async function embedContent(containerId, project, contentId) {
    const res = await fetch(`/v1/content/${project}/${contentId}`);
    const data = await res.json();

    // General layout
    const parentDiv = document.getElementById(containerId);
    parentDiv.innerHTML = `
        <div class="title" id="${containerId}-title">${data.content.title}</div>
        <div class="author" id="${containerId}-author">${data.content.username}</div>
        <div class="content" id="${containerId}-content"></div>
        <div class="tags-container" id="${containerId}-tags"></div>
    `;

    // Tags
    const tagsContainer = document.getElementById(`${containerId}-tags`);
    if (tagsContainer && data.content.tags && data.content.tags.length > 0) {
        data.content.tags.forEach(tag => {
            const tagSpan = document.createElement('span');
            tagSpan.textContent = tag;
            tagSpan.className = 'tag';
            tagsContainer.appendChild(tagSpan);
        });
    }

    // Embed the project-specific content
    const {embed} = await import(`/static/${project}/embed.js`);
    embed(`${containerId}-content`, data);
}

window.embedContent = embedContent;