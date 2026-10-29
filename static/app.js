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

function sendJson(url, method, body, errorMessage) {
    return fetchJson(url, {
        method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
        errorMessage,
    });
}

// Server-provided settings for the current project page.
function pageConfig() {
    const element = document.getElementById('page-config');
    return element ? JSON.parse(element.textContent) : {};
}

// Dialog state for creating or editing a collection.
function collectionForm(submit, onSaved) {
    return {
        formOpen: false,
        form: {},
        formError: '',
        pending: false,

        openForm(form = {title: '', description: '', is_public: false}) {
            this.form = form;
            this.formError = '';
            this.formOpen = true;
        },

        async submitForm() {
            this.pending = true;
            this.formError = '';
            try {
                const {collection} = await submit(this.form);
                this.formOpen = false;
                onSaved.call(this, collection);
            } catch (error) {
                this.formError = error.message;
            } finally {
                this.pending = false;
            }
        },
    };
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
    // x-modal="expression" shows a <dialog> as a modal while the expression is true.
    Alpine.directive('modal', (el, {expression}, {effect, evaluateLater}) => {
        const isOpen = evaluateLater(expression);
        effect(() => isOpen((open) => {
            if (open && !el.open) {
                el.showModal();
            } else if (!open && el.open) {
                el.close();
            }
        }));
    });

    // One confirmation dialog shared by all actions; ask() resolves to the user's choice.
    Alpine.store('confirm', {
        open: false,
        title: '',
        message: '',
        confirmLabel: '',
        danger: false,
        resolve: null,

        ask({title, message, confirmLabel = 'Confirm', danger = false}) {
            this.resolve?.(false);
            Object.assign(this, {title, message, confirmLabel, danger, open: true});
            return new Promise((resolve) => {
                this.resolve = resolve;
            });
        },

        close(confirmed) {
            this.open = false;
            this.resolve?.(confirmed);
            this.resolve = null;
        },
    });

    // A searchable multi-select dialog. onChange applies one changed item, onCreate optionally adds a new one.
    Alpine.store('picker', {
        open: false,
        title: '',
        message: '',
        emptyText: '',
        createLabel: '',
        searchable: false,
        items: [],
        search: '',
        pending: false,
        error: '',
        onChange: null,
        onCreate: null,

        show({
                 title, message = '', emptyText = 'Nothing found', createLabel = 'Create', searchable = false,
                 items, onChange, onCreate = null,
             }) {
            Object.assign(this, {
                title, message, emptyText, createLabel, searchable, onChange, onCreate,
                items: items.map((item) => ({...item, initial: item.selected})),
                search: '',
                error: '',
                pending: false,
                open: true,
            });
        },

        get visibleItems() {
            const search = this.search.trim().toLowerCase();
            return this.items.filter((item) => item.label.toLowerCase().includes(search));
        },

        get canCreate() {
            const search = this.search.trim().toLowerCase();
            return Boolean(this.onCreate && search && !this.items.some((item) => item.label.toLowerCase() === search));
        },

        async run(action) {
            this.pending = true;
            this.error = '';
            try {
                await action();
            } catch (error) {
                this.error = error.message;
            } finally {
                this.pending = false;
            }
        },

        create() {
            return this.run(async () => {
                const item = await this.onCreate(this.search.trim());
                this.items.unshift({...item, selected: true, initial: false});
                this.search = '';
            });
        },

        save() {
            return this.run(async () => {
                // Apply changes one by one so a failure keeps only the remaining ones pending.
                for (const item of this.items.filter((item) => item.selected !== item.initial)) {
                    await this.onChange(item);
                    item.initial = item.selected;
                }
                this.open = false;
            });
        },
    });

    // filters are fixed API parameters, e.g., the author on a user page.
    Alpine.data('contentList', (project, filters = {}) => ({
        ...pagedList({
            project,
            endpoint: sitePath('v3', 'content', project),
            itemsKey: 'contents',
            idName: 'content_id',
            itemUrl: (id) => sitePath(project, id),
            settings: {
                track: 'all', sort: 'recommendations', descending: 'true', limit: '8', search: '',
                similar_to: '', similar_to_collection: '',
            },
            query() {
                return {
                    ...filters,
                    author_id: this.track === 'submissions' ? 'me' : filters.author_id,
                    liked_by: this.track === 'likes' ? 'me' : filters.liked_by,
                    order: this.sort,
                    descending: this.descending,
                    q: this.search.trim(),
                    similar_to: this.similar_to,
                    similar_to_collection: this.similar_to_collection,
                    include_data: true,
                };
            },
        }),

        similarSource: '',

        similarSourceUrl() {
            return this.similar_to
                ? sitePath(project, this.similar_to)
                : sitePath(project, 'collections', this.similar_to_collection);
        },

        // Shows the title of what the list is similar to, falling back to a generic label.
        async loadSimilarSource() {
            const contentId = this.similar_to;
            const collectionId = this.similar_to_collection;
            this.similarSource = contentId ? 'this content' : 'this collection';
            if (!contentId && !collectionId) return;
            try {
                const data = contentId
                    ? await fetchJson(sitePath('v3', 'content', project, contentId))
                    : await fetchJson(sitePath('v1', 'collection', project, collectionId));
                if (contentId === this.similar_to && collectionId === this.similar_to_collection) {
                    this.similarSource = (data.content ?? data.collection).title;
                }
            } catch {
                // The generic label stays.
            }
        },

        clearSimilar() {
            this.similar_to = '';
            this.similar_to_collection = '';
            this.changeSetting();
        },

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
        settings: {sort: 'likes_received', descending: 'true', limit: '24', search: ''},
        query() {
            return {order: this.sort, descending: this.descending, q: this.search.trim()};
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

    Alpine.data('collectionCreate', (project) => collectionForm(
        (form) => sendJson(sitePath('v1', 'collection', project), 'POST', form, 'Unable to create collection'),
        (collection) => window.location.assign(sitePath(project, 'collections', collection.collection_id)),
    ));

    Alpine.data('collectionDetail', (project, collectionId) => {
        const collectionUrl = sitePath('v1', 'collection', project, collectionId);

        return {
            project,
            collection: null,
            error: '',
            ...collectionForm((form) => sendJson(collectionUrl, 'PATCH', form, 'Unable to save collection'), function (collection) {
                this.collection = collection;
                document.title = collection.title;
            }),

            async init() {
                try {
                    await this.$store.auth.loadUser(project);
                    const data = await fetchJson(collectionUrl, {errorMessage: 'Unable to load collection'});
                    this.collection = data.collection;
                    document.title = this.collection.title;
                } catch (error) {
                    this.error = error.message;
                }
            },

            openEdit() {
                const {title, description, is_public} = this.collection;
                this.openForm({title, description, is_public});
            },

            similarUrl() {
                return `${sitePath(project)}?${new URLSearchParams({similar_to_collection: collectionId})}`;
            },

            async deleteCollection() {
                const confirmed = await this.$store.confirm.ask({
                    title: 'Delete collection',
                    message: `Delete "${this.collection.title}"? The content itself is kept.`,
                    confirmLabel: 'Delete',
                    danger: true,
                });
                if (!confirmed) return;
                try {
                    await fetchJson(collectionUrl, {method: 'DELETE', errorMessage: 'Unable to delete collection'});
                    window.location.assign(sitePath(project, 'collections'));
                } catch (error) {
                    alert(error.message);
                }
            },
        };
    });

    Alpine.data('userDetail', (project, user) => ({
        item: user,
        pending: false,

        async init() {
            await this.$store.auth.loadUser(project);
        },

        get canModerate() {
            const viewer = this.$store.auth.user;
            return Boolean(viewer?.moderator && viewer.user_id !== this.item.user_id);
        },

        async moderate({parameters, done, ...dialog}) {
            if (this.pending || !await this.$store.confirm.ask(dialog)) return;
            this.pending = true;
            try {
                const url = `${sitePath('v1', 'user', this.item.user_id)}?${new URLSearchParams(parameters)}`;
                await fetchJson(url, {method: 'PUT', errorMessage: 'Moderation failed'});
                done();
            } catch (error) {
                alert(error.message);
            } finally {
                this.pending = false;
            }
        },

        setModerator(moderator) {
            return this.moderate({
                title: moderator ? 'Promote user' : 'Demote user',
                message: moderator
                    ? `Make ${this.item.username} a moderator? Moderators can delete any content and moderate users.`
                    : `Remove moderator status from ${this.item.username}?`,
                confirmLabel: moderator ? 'Promote' : 'Demote',
                parameters: {moderator},
                done: () => {
                    this.item.moderator = moderator;
                },
            });
        },

        ban() {
            return this.moderate({
                title: 'Ban user',
                message: `Ban ${this.item.username}? Banned users can no longer sign in, and their content is hidden.`,
                confirmLabel: 'Ban',
                danger: true,
                parameters: {banned: true},
                done: () => window.location.assign(sitePath(project, 'users')),
            });
        },

        purge() {
            return this.moderate({
                title: 'Purge user',
                message: `Permanently delete all content and likes of ${this.item.username}? This cannot be undone.`,
                confirmLabel: 'Purge',
                danger: true,
                parameters: {purge: true},
                done: () => window.location.reload(),
            });
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
            reportReasons: pageConfig().reportReasons ?? {},
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
                const {is_liked: liked, likes} = this.content;
                this.content.is_liked = !liked;
                this.content.likes = likes + (liked ? -1 : 1);
                try {
                    await fetchJson(sitePath('v1', 'like', project, contentId), {
                        method: liked ? 'DELETE' : 'POST',
                        errorMessage: 'Unable to update like',
                        // A repeated request can already be in the desired state.
                        allowedStatuses: [428],
                    });
                    this.$dispatch('content-like-changed', {contentId, liked: !liked});
                } catch (error) {
                    this.content.is_liked = liked;
                    this.content.likes = likes;
                    if (!controller.signal.aborted) {
                        alert(error.message);
                    }
                    return;
                } finally {
                    this.pending = false;
                }

                // Revalidate this item's cached viewer state in the background.
                this.fetchContent(true).then((refreshed) => {
                    this.content.is_liked = refreshed.is_liked;
                    this.content.likes = refreshed.likes;
                }).catch(() => {
                });
            },

            requireUser() {
                if (this.$store.auth.user) return true;
                this.$store.auth.login();
                return false;
            },

            async editCollections() {
                if (!this.requireUser()) return;
                const collectionsUrl = sitePath('v1', 'collection', project);
                try {
                    const parameters = new URLSearchParams({user_id: 'me', content_id: contentId, limit: 500});
                    const {collections} = await fetchJson(`${collectionsUrl}?${parameters}`, {
                        errorMessage: 'Unable to load collections',
                    });
                    this.$store.picker.show({
                        title: 'Collections',
                        message: `Choose the collections that contain "${this.content.title}".`,
                        emptyText: 'Type a name to create a collection.',
                        createLabel: 'Create collection',
                        searchable: true,
                        items: collections.map((collection) => ({
                            id: collection.collection_id,
                            label: collection.title,
                            selected: collection.contains_content,
                        })),
                        onCreate: async (title) => {
                            const {collection} = await sendJson(collectionsUrl, 'POST', {title}, 'Unable to create collection');
                            return {id: collection.collection_id, label: collection.title};
                        },
                        onChange: (item) => fetchJson(sitePath('v1', 'collection', project, item.id, 'content', contentId), {
                            method: item.selected ? 'PUT' : 'DELETE',
                            errorMessage: 'Unable to update collection',
                        }),
                    });
                } catch (error) {
                    alert(error.message);
                }
            },

            report() {
                if (!this.requireUser()) return;
                this.$store.picker.show({
                    title: 'Report content',
                    message: `Why are you reporting "${this.content.title}"?`,
                    items: Object.entries(this.reportReasons).map(([reason, label]) => ({
                        id: reason,
                        label,
                        selected: this.content.reports.includes(reason),
                    })),
                    onChange: async (item) => {
                        await fetchJson(sitePath('v1', 'report', project, contentId, item.id), {
                            method: item.selected ? 'POST' : 'DELETE',
                            errorMessage: 'Unable to update report',
                            // A repeated request can already be in the desired state.
                            allowedStatuses: [428],
                        });
                        this.content.reports = item.selected
                            ? [...this.content.reports, item.id]
                            : this.content.reports.filter((reason) => reason !== item.id);
                    },
                });
            },

            // Reviewed content is no longer hidden by reports.
            async markReviewed() {
                if (this.pending) return;
                this.pending = true;
                try {
                    await fetchJson(sitePath('v1', 'report', project, contentId, 'REVIEWED'), {
                        method: 'POST',
                        errorMessage: 'Unable to mark as reviewed',
                        allowedStatuses: [428],
                    });
                    this.$dispatch('content-reviewed', contentId);
                } catch (error) {
                    alert(error.message);
                } finally {
                    this.pending = false;
                }
            },

            async deleteContent() {
                if (this.pending || !this.canDelete) return;
                const confirmed = await this.$store.confirm.ask({
                    title: 'Delete content',
                    message: `Delete "${this.content.title}"? This cannot be undone.`,
                    confirmLabel: 'Delete',
                    danger: true,
                });
                if (!confirmed) return;

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

            similarUrl() {
                return `${sitePath(project)}?${new URLSearchParams({similar_to: contentId})}`;
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
