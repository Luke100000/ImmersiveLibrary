document.addEventListener('alpine:init', () => {
    Alpine.data('libraryBrowser', () => {
        let loadVersion = 0;

        return {
            project: '',
            track: 'all',
            sort: 'recommendations',
            descending: 'true',
            limit: '8',
            page: 1,
            search: '',
            authenticated: false,
            contents: [],
            loading: true,
            error: '',
            hasMore: false,

            async init() {
                const parameters = new URLSearchParams(window.location.search);
                for (const select of this.$el.querySelectorAll('select')) {
                    const value = parameters.get(select.name);
                    this[select.name] = [...select.options].some((option) => option.value === value)
                        ? value : select.value;
                }
                const page = Number.parseInt(parameters.get('page'), 10);
                this.page = Number.isSafeInteger(page) && page > 0 ? page : 1;
                this.search = parameters.get('search') || '';

                try {
                    const response = await fetch('/v1/auth');
                    this.authenticated = response.ok && (await response.json()).authenticated === true;
                } catch {
                    this.authenticated = false;
                }

                if (!this.authenticated && this.track !== 'all') {
                    this.navigate({track: 'all', page: 1});
                    return;
                }
                await this.loadContent();
            },

            urlWith(parameters) {
                const url = new URL(window.location.href);
                for (const [name, value] of Object.entries(parameters)) {
                    if (value === '') {
                        url.searchParams.delete(name);
                    } else {
                        url.searchParams.set(name, value);
                    }
                }
                return url;
            },

            navigate(parameters) {
                window.location.assign(this.urlWith(parameters));
            },

            searchContent() {
                this.page = 1;
                window.history.replaceState(null, '', this.urlWith({search: this.search.trim(), page: 1}));
                this.loadContent();
            },

            async loadContent() {
                const version = ++loadVersion;
                this.loading = true;
                this.contents = [];
                this.error = '';
                this.hasMore = false;

                const url = new URL(`/v3/content/${encodeURIComponent(this.project)}`, window.location.origin);
                if (this.track === 'likes') {
                    url.searchParams.set('liked_by', 'me');
                } else if (this.track === 'submissions') {
                    url.searchParams.set('author_id', 'me');
                }
                url.searchParams.set('order', this.sort);
                url.searchParams.set('descending', this.descending);
                url.searchParams.set('limit', this.limit);
                url.searchParams.set('offset', (this.page - 1) * Number(this.limit));
                if (this.search.trim()) {
                    url.searchParams.set('q', this.search.trim());
                }

                try {
                    const response = await fetch(url);
                    const data = await response.json();
                    if (version !== loadVersion) return;
                    if (!response.ok) {
                        throw new Error(data.message || 'Unable to load content');
                    }
                    this.contents = data.contents;
                    this.hasMore = data.has_more;
                } catch (error) {
                    if (version === loadVersion) {
                        this.error = error.message;
                    }
                } finally {
                    if (version === loadVersion) {
                        this.loading = false;
                    }
                }
            },

            contentUrl(contentId) {
                return `/${encodeURIComponent(this.project)}/${contentId}`;
            },

            async deleteContent(contentId) {
                if (!window.confirm(`Are you sure you want to delete content #${contentId}?`)) return;

                try {
                    const response = await fetch(`/v1/content/${encodeURIComponent(this.project)}/${contentId}`, {method: 'DELETE'});
                    if (response.ok) {
                        this.contents = this.contents.filter((content) => content.content_id !== contentId);
                    } else if (response.status === 401 || response.status === 403) {
                        alert('Not allowed to delete this content.');
                    } else if (response.status === 404) {
                        alert('Content not found.');
                    } else {
                        alert(`Delete failed (${response.status}).`);
                    }
                } catch {
                    alert('Network error while deleting.');
                }
            },
        };
    });

    Alpine.data('contentPreview', (project, initialContent) => {
        const controller = new AbortController();
        let unregister;

        return {
            content: null,
            loading: true,
            error: '',
            loadingLabel: typeof initialContent === 'number' ? `Loading #${initialContent}...` : 'Loading...',

            async init() {
                try {
                    if (typeof initialContent === 'number') {
                        const response = await fetch(`/v3/content/${encodeURIComponent(project)}/${initialContent}`, {signal: controller.signal});
                        const data = await response.json();
                        if (!response.ok) {
                            throw new Error(data.message || 'Unable to load content');
                        }
                        this.content = data.content;
                    } else {
                        this.content = initialContent;
                    }
                    this.loading = false;
                    await this.$nextTick();
                    if (controller.signal.aborted) return;

                    unregister = await embedContentPreview(this.$refs.preview, project, this.content);
                    if (controller.signal.aborted) {
                        unregister?.();
                    }
                } catch (error) {
                    if (!controller.signal.aborted) {
                        this.error = error.message;
                        this.loading = false;
                    }
                }
            },

            searchUrl(search) {
                const url = new URL('/', window.location.origin);
                url.searchParams.set('project', project);
                url.searchParams.set('search', search);
                return url.href;
            },

            destroy() {
                controller.abort();
                unregister?.();
            },
        };
    });
});
