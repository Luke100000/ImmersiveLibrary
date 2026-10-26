async function fetchJson(url, {errorMessage = 'Request failed', allowedStatuses = [], ...options} = {}) {
    const response = await fetch(url, options);
    // Error responses are not guaranteed to be JSON, e.g., proxy errors.
    const data = await response.json().catch(() => ({}));
    if (!response.ok && !allowedStatuses.includes(response.status)) {
        throw new Error(data.message || `${errorMessage} (${response.status})`);
    }
    return data;
}

function plural(count, noun, suffix = '') {
    return `${count.toLocaleString()} ${noun}${count === 1 ? '' : 's'}${suffix}`;
}

function sitePath(...parts) {
    return '/' + parts.map((part) => encodeURIComponent(part)).join('/');
}

// Shared state for a paged API list. Settings mirror the controls and, with syncUrl, the query string.
function pagedList({project, endpoint, itemsKey, idName, itemUrl, settings, query, syncUrl = true}) {
    let loadVersion = 0;

    return {
        ...settings,
        project,
        page: 1,
        items: [],
        loading: true,
        error: '',
        hasMore: false,
        authenticated: false,

        async init() {
            if (syncUrl) {
                this.readUrl();
            }
            this.authenticated = Boolean(await this.$store.auth.loadUser(project));
            if (!this.authenticated && 'track' in settings) {
                this.track = settings.track;
            }
            await this.load();
        },

        readUrl() {
            const parameters = new URLSearchParams(window.location.search);
            for (const name of Object.keys(settings)) {
                const value = parameters.get(name);
                const select = this.$root.querySelector(`select[name="${name}"]`);
                if (value !== null && (!select || [...select.options].some((option) => option.value === value))) {
                    this[name] = value;
                }
            }
            const page = Number.parseInt(parameters.get('page'), 10);
            this.page = Number.isSafeInteger(page) && page > 0 ? page : 1;
        },

        writeUrl() {
            const url = new URL(window.location.href);
            const defaults = {...settings, page: 1};
            for (const name of Object.keys(defaults)) {
                const value = typeof this[name] === 'string' ? this[name].trim() : this[name];
                if (value === defaults[name]) {
                    url.searchParams.delete(name);
                } else {
                    url.searchParams.set(name, value);
                }
            }
            window.history.replaceState(null, '', url);
        },

        changeSetting() {
            this.page = 1;
            this.load();
        },

        goToPage(page) {
            this.page = page;
            this.load();
            this.$root.scrollIntoView({block: 'start'});
        },

        async load() {
            const version = ++loadVersion;
            this.loading = true;
            this.error = '';
            if (syncUrl) {
                this.writeUrl();
            }

            const url = new URL(endpoint, window.location.origin);
            const parameters = {
                ...query.call(this),
                limit: this.limit,
                offset: (this.page - 1) * Number(this.limit),
            };
            for (const [name, value] of Object.entries(parameters)) {
                if (value !== undefined && value !== '') {
                    url.searchParams.set(name, value);
                }
            }

            try {
                const data = await fetchJson(url, {errorMessage: 'Unable to load list'});
                if (version !== loadVersion) return;
                this.items = data[itemsKey];
                this.hasMore = data.has_more;
            } catch (error) {
                if (version === loadVersion) {
                    this.error = error.message;
                    this.items = [];
                    this.hasMore = false;
                }
            } finally {
                if (version === loadVersion) {
                    this.loading = false;
                }
            }
        },

        itemUrl,

        removeItem(id) {
            this.items = this.items.filter((item) => item[idName] !== id);
        },
    };
}

document.addEventListener('alpine:init', () => {
    // filters are fixed API parameters, e.g., the author on a user page.
    Alpine.data('contentList', (project, filters = {}) => ({
        ...pagedList({
            project,
            endpoint: sitePath('v3', 'content', project),
            itemsKey: 'contents',
            idName: 'content_id',
            itemUrl: (id) => sitePath(project, id),
            settings: {track: 'all', sort: 'recommendations', descending: 'true', limit: '8', search: ''},
            query() {
                return {
                    ...filters,
                    author_id: this.track === 'submissions' ? 'me' : filters.author_id,
                    liked_by: this.track === 'likes' ? 'me' : filters.liked_by,
                    order: this.sort,
                    descending: this.descending,
                    q: this.search.trim(),
                };
            },
        }),

        likeChanged({contentId, liked}) {
            if (this.track === 'likes' && !liked) {
                this.removeItem(contentId);
            }
        },
    }));

    Alpine.data('userList', (project) => pagedList({
        project,
        endpoint: sitePath('v3', 'user', project),
        itemsKey: 'users',
        idName: 'user_id',
        itemUrl: (id) => sitePath(project, 'users', id),
        settings: {sort: 'likes_received', descending: 'true', limit: '24'},
        query() {
            return {order: this.sort, descending: this.descending};
        },
    }));

    Alpine.data('collectionList', (project, filters = {}, syncUrl = true) => pagedList({
        project,
        syncUrl,
        endpoint: sitePath('v1', 'collection', project),
        itemsKey: 'collections',
        idName: 'collection_id',
        itemUrl: (id) => sitePath(project, 'collections', id),
        settings: {track: 'all', limit: '24', search: ''},
        query() {
            return {
                ...filters,
                user_id: this.track === 'mine' ? 'me' : filters.user_id,
                q: this.search.trim(),
            };
        },
    }));

    Alpine.data('collectionDetail', (project, collectionId) => ({
        project,
        collection: null,
        error: '',

        async init() {
            try {
                await this.$store.auth.loadUser(project);
                const data = await fetchJson(sitePath('v1', 'collection', project, collectionId), {
                    errorMessage: 'Unable to load collection',
                });
                this.collection = data.collection;
                document.title = this.collection.title;
            } catch (error) {
                this.error = error.message;
            }
        },
    }));

    // initialContent is a content id, a content summary, or a full content object.
    Alpine.data('contentPreview', (project, initialContent, mode = 'card') => {
        const controller = new AbortController();
        const contentId = typeof initialContent === 'number' ? initialContent : initialContent.content_id;
        let unregister;

        return {
            content: typeof initialContent === 'number' ? null : initialContent,
            loading: true,
            error: '',
            pending: false,
            isDetail: mode === 'detail',
            showActions: mode !== 'preview',
            backUrl: sitePath(project),

            async init() {
                try {
                    if (this.isDetail && document.referrer) {
                        const previous = new URL(document.referrer);
                        if (previous.origin === window.location.origin && previous.href !== window.location.href) {
                            this.backUrl = previous.href;
                        }
                    }
                    if (this.showActions) {
                        await this.$store.auth.loadUser(project);
                    }
                    // Summaries lack the data payload, and server-rendered content lacks the viewer's like state.
                    if (!this.content?.data || (this.isDetail && this.$store.auth.user)) {
                        this.content = await this.fetchContent();
                    }
                    this.$dispatch('content-like-changed', {contentId, liked: this.content.is_liked});
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

            get canDelete() {
                const user = this.$store.auth.user;
                return Boolean(user && (user.moderator || user.user_id === this.content?.user_id));
            },

            async fetchContent(refresh = false) {
                const data = await fetchJson(sitePath('v3', 'content', project, contentId), {
                    signal: controller.signal,
                    headers: refresh ? {'Cache-Control': 'no-cache'} : {},
                    errorMessage: 'Unable to load content',
                });
                return data.content;
            },

            async toggleLike() {
                if (this.pending) return;
                if (!this.$store.auth.user) {
                    this.$store.auth.login();
                    return;
                }

                this.pending = true;
                const liked = this.content.is_liked;
                try {
                    await fetchJson(sitePath('v1', 'like', project, contentId), {
                        method: liked ? 'DELETE' : 'POST',
                        errorMessage: 'Unable to update like',
                        // A repeated request can already be in the desired state.
                        allowedStatuses: [428],
                    });
                    this.content.is_liked = !liked;
                    // Revalidate this item's cached viewer state after the mutation.
                    const refreshed = await this.fetchContent(true);
                    this.content.is_liked = refreshed.is_liked;
                    this.content.likes = refreshed.likes;
                    this.$dispatch('content-like-changed', {contentId, liked: this.content.is_liked});
                } catch (error) {
                    if (!controller.signal.aborted) {
                        alert(error.message);
                    }
                } finally {
                    this.pending = false;
                }
            },

            async deleteContent() {
                if (this.pending || !this.canDelete) return;
                if (!window.confirm(`Are you sure you want to delete content #${contentId}?`)) return;

                this.pending = true;
                try {
                    await fetchJson(sitePath('v1', 'content', project, contentId), {
                        method: 'DELETE',
                        errorMessage: 'Delete failed',
                    });
                    this.$dispatch('content-deleted', contentId);
                    if (this.isDetail) {
                        window.location.assign(this.backUrl);
                    }
                } catch (error) {
                    alert(error.message);
                } finally {
                    this.pending = false;
                }
            },

            formatTag(tag) {
                return tag.replaceAll('_', ' ').toLowerCase()
                    .replace(/(^|\s)\S/g, letter => letter.toUpperCase());
            },

            searchUrl(search) {
                return `${sitePath(project)}?${new URLSearchParams({search})}`;
            },

            userUrl() {
                return sitePath(project, 'users', this.content.user_id);
            },

            destroy() {
                controller.abort();
                unregister?.();
            },
        };
    });
});
