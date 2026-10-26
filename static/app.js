async function fetchJson(url, {errorMessage = 'Request failed', allowedStatuses = [], ...options} = {}) {
    const response = await fetch(url, options);
    // Error responses are not guaranteed to be JSON, e.g., proxy errors.
    const data = await response.json().catch(() => ({}));
    if (!response.ok && !allowedStatuses.includes(response.status)) {
        throw new Error(data.message || `${errorMessage} (${response.status})`);
    }
    return data;
}

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

                this.authenticated = Boolean(await this.$store.auth.loadUser(this.project));

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

            changeSetting(name) {
                this.navigate({[name]: this[name], page: 1});
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
                    const data = await fetchJson(url, {errorMessage: 'Unable to load content'});
                    if (version !== loadVersion) return;
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

            openContent(contentId) {
                window.location.assign(`/${encodeURIComponent(this.project)}/${contentId}`);
            },

            removeContent(contentId) {
                this.contents = this.contents.filter((content) => content.content_id !== contentId);
            },

            likeChanged({contentId, liked}) {
                if (this.track === 'likes' && !liked) {
                    this.removeContent(contentId);
                }
            },
        };
    });

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
            backUrl: '/',

            async init() {
                try {
                    if (this.isDetail && document.referrer) {
                        const previous = new URL(document.referrer);
                        if (previous.origin === window.location.origin && previous.pathname === '/') {
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
                const data = await fetchJson(`/v3/content/${encodeURIComponent(project)}/${contentId}`, {
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
                    await fetchJson(`/v1/like/${encodeURIComponent(project)}/${contentId}`, {
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
                    await fetchJson(`/v1/content/${encodeURIComponent(project)}/${contentId}`, {
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
