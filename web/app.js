const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

const STORAGE_KEYS = {
    searchHistory: "readerSearchHistory",
    recentBooks: "readerRecentBooks",
};

const readStoredArray = (key) => {
    try {
        const value = JSON.parse(localStorage.getItem(key) || "[]");
        return Array.isArray(value) ? value : [];
    } catch (error) {
        return [];
    }
};

const writeStoredArray = (key, value) => {
    localStorage.setItem(key, JSON.stringify(value));
};

const BookCover = {
    props: {
        src: { type: String, default: "" },
        title: { type: String, default: "" },
    },
    data() {
        return { failed: false };
    },
    computed: {
        initial() {
            const text = String(this.title || "书").trim();
            return text ? text.slice(0, 1) : "书";
        },
    },
    watch: {
        src() {
            this.failed = false;
        },
    },
    template: `
        <span class="book-cover">
            <img v-if="src && !failed" :src="src" :alt="title" @error="failed = true">
            <span v-else class="book-cover-placeholder">{{ initial }}</span>
        </span>
    `,
};

createApp({
    components: { BookCover },
    setup() {
        const view = ref("search");
        const keyword = ref("");
        const books = ref([]);
        const shelf = ref([]);
        const suggestions = ref([]);
        const showSuggestions = ref(false);
        const hasSearched = ref(false);
        const selectedSourceFilter = ref("");
        const selectedBook = ref(null);
        const chapters = ref([]);
        const currentContent = ref("");
        const currentBook = ref(null);
        const currentChapterTitle = ref("");
        const currentChapterIndex = ref(-1);
        const contentIsCached = ref(false);
        const fontSize = ref(Number(localStorage.getItem("readerFontSize") || 18));
        const theme = ref(localStorage.getItem("readerTheme") || "eye");
        const loading = ref(false);
        const loadingText = ref("加载中");
        const activeTag = ref("");
        const editingTagsAid = ref("");
        const tagDraft = ref("");
        const cachingAid = ref("");
        const cacheProgress = ref({ current: 0, total: 0 });
        const downloadingKey = ref("");
        const scrollPane = ref(null);
        const toasts = ref([]);
        const searchHistory = ref(readStoredArray(STORAGE_KEYS.searchHistory));
        const recentBooks = ref(readStoredArray(STORAGE_KEYS.recentBooks));
        let suggestTimer = null;
        let toastId = 1;

        const sourcesList = ref([]);
        const showSourceForm = ref(false);
        const editingSource = ref(null);
        const sourceForm = ref({
            name: "",
            base_url: "",
            color: "#4F46E5",
            search_path: "/api/novel/search?q={query}&page={page}&limit=20&lang=zh-CN",
            chapter_list_path: "/api/chapter/list/{aid}?lang=zh-CN",
            chapter_content_path: "/api/chapter/content/{aid}/{cid}?lang=zh-CN",
            field_map: { name: "articlename", author: "author", aid: "articleid", cover: "cover", intro: "intro" },
        });

        const themes = [
            { key: "eye", name: "护眼模式", swatch: "bg-[#fbfff4] text-[#9ab986]" },
            { key: "night", name: "夜间模式", swatch: "bg-black text-slate-500" },
            { key: "parchment", name: "羊皮纸模式", swatch: "bg-[#f7ebcd] text-[#b99352]" },
        ];
        const quickTerms = ["凡人修仙传", "斗破苍穹", "诡秘之主", "庆余年", "吞噬星空", "完美世界"];

        const readerThemeClass = computed(() => `theme-${theme.value}`);
        const allTags = computed(() => {
            const tags = new Set();
            shelf.value.forEach(book => (book.tags || []).forEach(tag => tags.add(tag)));
            return Array.from(tags);
        });
        const filteredShelf = computed(() => {
            if (!activeTag.value) return shelf.value;
            return shelf.value.filter(book => (book.tags || []).includes(activeTag.value));
        });
        const enabledSourceCount = computed(() => sourcesList.value.filter(src => src.enabled !== false).length);
        const cachedBookCount = computed(() => shelf.value.filter(book => book.cached).length);
        const filteredBooks = computed(() => {
            if (!selectedSourceFilter.value) return books.value;
            return books.value.filter(book => book.source_id === selectedSourceFilter.value);
        });
        const recentDisplayBooks = computed(() => {
            if (recentBooks.value.length) return recentBooks.value.slice(0, 6);
            return shelf.value.slice(0, 6);
        });
        const cachePercent = computed(() => {
            if (!cacheProgress.value.total) return 0;
            return Math.round(cacheProgress.value.current / cacheProgress.value.total * 100);
        });
        const selectedBookProgress = computed(() => {
            if (!selectedBook.value) return null;
            return selectedBook.value.progress || findShelfBook(selectedBook.value)?.progress || null;
        });

        watch(fontSize, value => localStorage.setItem("readerFontSize", value));

        const toast = (message, type = "success") => {
            const id = toastId++;
            toasts.value.push({ id, message, type });
            window.setTimeout(() => {
                toasts.value = toasts.value.filter(item => item.id !== id);
            }, 3200);
        };

        const fetchJson = async (url, options = {}) => {
            const res = await fetch(url, options);
            if (!res.ok) {
                let detail = `${res.status}`;
                try {
                    const body = await res.json();
                    detail = body.detail || body.msg || detail;
                } catch (error) {}
                throw new Error(detail);
            }
            return res.json();
        };

        const icon = (name) => {
            const icons = {
                "alert-circle": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
                "arrow-left": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 19-7-7 7-7"/><path d="M19 12H5"/></svg>',
                "arrow-right": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>',
                bookmark: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>',
                "book-open": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
                "check-circle": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
                "chevron-left": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>',
                "chevron-right": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>',
                clock: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
                database: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg>',
                download: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
                "file-text": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg>',
                globe: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>',
                library: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/></svg>',
                list: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>',
                pencil: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
                play: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></svg>',
                plus: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
                "refresh-cw": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>',
                search: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
                tag: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/></svg>',
                "toggle-left": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="12" x="2" y="6" rx="6"/><circle cx="8" cy="12" r="2"/></svg>',
                "toggle-right": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="12" x="2" y="6" rx="6"/><circle cx="16" cy="12" r="2"/></svg>',
                "trash-2": '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>',
                x: '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
            };
            return icons[name] || "";
        };

        const navClass = (active) => ["nav-item", active ? "active" : ""];
        const filterClass = (active) => ["filter-button", active ? "active" : ""];

        const setView = (nextView) => {
            view.value = nextView;
            showSuggestions.value = false;
            if (nextView !== "search") {
                selectedBook.value = null;
            }
            nextTick(() => scrollPane.value?.scrollTo(0, 0));
        };

        const setTheme = (key) => {
            theme.value = key;
            localStorage.setItem("readerTheme", key);
        };

        const getCover = (id) => {
            const numeric = Number(id);
            if (!Number.isFinite(numeric) || numeric <= 0) return "";
            return `https://pic.cooks.tw/${Math.floor(numeric / 1000)}/${id}/${id}s.jpg`;
        };
        const bookAid = (book) => String(book?.articleid || book?.aid || "");
        const bookName = (book) => book?.articlename || book?.name || "";
        const bookAuthor = (book) => book?.author || "";
        const bookCover = (book) => book?.cover || getCover(bookAid(book));

        const findShelfBook = (book) => {
            const aid = bookAid(book);
            if (!aid) return null;
            return shelf.value.find(item => String(item.aid) === aid) || null;
        };

        const getSourceName = (sid) => {
            if (!sid) return "";
            const s = sourcesList.value.find(x => x.id === sid);
            return s ? s.name : "";
        };

        const getSourceColor = (sid) => {
            if (!sid) return "#64748b";
            const s = sourcesList.value.find(x => x.id === sid);
            return s ? (s.color || "#64748b") : "#64748b";
        };

        const sourceResultCount = (sourceId) => books.value.filter(book => book.source_id === sourceId).length;

        const normalizeRecentBook = (book) => {
            const shelfBook = findShelfBook(book);
            return {
                aid: bookAid(book),
                name: bookName(book),
                author: bookAuthor(book),
                cover: bookCover(book),
                source_id: book?.source_id || "",
                progress: book?.progress || shelfBook?.progress || null,
            };
        };

        const rememberBook = (book) => {
            const normalized = normalizeRecentBook(book);
            if (!normalized.aid) return;
            const next = [
                normalized,
                ...recentBooks.value.filter(item => !(String(item.aid) === normalized.aid && item.source_id === normalized.source_id)),
            ].slice(0, 6);
            recentBooks.value = next;
            writeStoredArray(STORAGE_KEYS.recentBooks, next);
        };

        const updateRecentProgress = (aid, progress) => {
            const next = recentBooks.value.map(item => String(item.aid) === String(aid) ? { ...item, progress } : item);
            recentBooks.value = next;
            writeStoredArray(STORAGE_KEYS.recentBooks, next);
        };

        const rememberSearch = (text) => {
            const value = text.trim();
            if (!value) return;
            const next = [value, ...searchHistory.value.filter(item => item !== value)].slice(0, 8);
            searchHistory.value = next;
            writeStoredArray(STORAGE_KEYS.searchHistory, next);
        };

        const clearSearchHistory = () => {
            searchHistory.value = [];
            writeStoredArray(STORAGE_KEYS.searchHistory, []);
            toast("搜索历史已清空");
        };

        const doSearch = async () => {
            const text = keyword.value.trim();
            if (!text) {
                toast("请输入书名或作者", "error");
                return;
            }
            loading.value = true;
            loadingText.value = "搜索中";
            setView("search");
            selectedBook.value = null;
            try {
                const json = await fetchJson(`/api/search/?q=${encodeURIComponent(text)}`);
                books.value = json.data?.items || [];
                hasSearched.value = true;
                showSuggestions.value = false;
                rememberSearch(text);
                if (!books.value.length) {
                    toast("没有找到相关书籍", "error");
                }
            } catch (error) {
                toast(`搜索失败：${error.message}`, "error");
            } finally {
                loading.value = false;
            }
        };

        const fetchSuggestions = () => {
            clearTimeout(suggestTimer);
            const text = keyword.value.trim();
            if (!text) {
                suggestions.value = [];
                showSuggestions.value = false;
                hasSearched.value = false;
                books.value = [];
                return;
            }
            suggestTimer = setTimeout(async () => {
                try {
                    const json = await fetchJson(`/api/search/suggest?q=${encodeURIComponent(text)}`);
                    suggestions.value = json.suggestions || [];
                    showSuggestions.value = suggestions.value.length > 0;
                } catch (error) {
                    suggestions.value = [];
                }
            }, 240);
        };

        const chooseSuggestion = (item) => {
            keyword.value = item.name;
            showSuggestions.value = false;
            doSearch();
        };

        const searchTerm = (term) => {
            keyword.value = term;
            showSuggestions.value = false;
            doSearch();
        };

        const openBookDetails = (book) => {
            selectedBook.value = {
                ...book,
                progress: book.progress || findShelfBook(book)?.progress || null,
            };
        };

        const closeBookDetails = () => {
            selectedBook.value = null;
        };

        const startSelectedBook = async (autoResume) => {
            if (!selectedBook.value) return;
            await openBook({
                ...selectedBook.value,
                progress: selectedBookProgress.value,
            }, autoResume);
            closeBookDetails();
        };

        const loadShelf = async () => {
            try {
                const data = await fetchJson("/api/bookshelf/");
                shelf.value = Array.isArray(data) ? data : [];
            } catch (error) {
                shelf.value = [];
                toast(`书架加载失败：${error.message}`, "error");
            }
        };

        const openShelf = async () => {
            setView("shelf");
            loading.value = true;
            loadingText.value = "加载书架";
            await loadShelf();
            loading.value = false;
        };

        const addToShelf = async (book) => {
            const aid = bookAid(book);
            if (!aid) {
                toast("这本书缺少书籍 ID，无法加入书架", "error");
                return;
            }
            try {
                await fetchJson("/api/bookshelf/add", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        aid,
                        name: bookName(book),
                        author: bookAuthor(book),
                        cover: bookCover(book),
                        source_id: book.source_id || "",
                    }),
                });
                await loadShelf();
                toast("已加入书架");
                if (selectedBook.value && bookAid(selectedBook.value) === aid) {
                    selectedBook.value = { ...selectedBook.value, progress: findShelfBook(book)?.progress || null };
                }
            } catch (error) {
                toast(`加入书架失败：${error.message}`, "error");
            }
        };

        const removeFromShelf = async (aid) => {
            if (!aid || !confirm("确认删除此书？将同时清除本地缓存。")) return;
            try {
                await fetchJson(`/api/bookshelf/remove/${encodeURIComponent(aid)}`, { method: "DELETE" });
                await loadShelf();
                toast("已从书架移除");
            } catch (error) {
                toast(`移除失败：${error.message}`, "error");
            }
        };

        const checkUpdates = async () => {
            loading.value = true;
            loadingText.value = "检查更新";
            try {
                const data = await fetchJson("/api/bookshelf/check-updates", { method: "POST" });
                shelf.value = Array.isArray(data) ? data : [];
                toast("更新检查完成");
            } catch (error) {
                toast(`检查更新失败：${error.message}`, "error");
            } finally {
                loading.value = false;
            }
        };

        const clearBookCache = async (book) => {
            if (!confirm(`确认清除「${book.name}」的本地缓存？`)) return;
            try {
                await fetchJson(`/api/reader/cache/${encodeURIComponent(book.aid)}`, { method: "DELETE" });
                await loadShelf();
                toast("缓存已清除");
            } catch (error) {
                toast(`清除缓存失败：${error.message}`, "error");
            }
        };

        const clearAllCache = async () => {
            if (!confirm("确认清除所有书籍的本地缓存？")) return;
            try {
                await fetchJson("/api/reader/cache", { method: "DELETE" });
                await loadShelf();
                toast("全部缓存已清除");
            } catch (error) {
                toast(`清除缓存失败：${error.message}`, "error");
            }
        };

        const startTagEdit = (book) => {
            editingTagsAid.value = book.aid;
            tagDraft.value = (book.tags || []).join(", ");
        };

        const saveTags = async (book) => {
            const tags = tagDraft.value.split(/[,，\s]+/).map(item => item.trim()).filter(Boolean);
            try {
                await fetchJson(`/api/bookshelf/tags/${encodeURIComponent(book.aid)}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tags }),
                });
                editingTagsAid.value = "";
                await loadShelf();
                toast("标签已保存");
            } catch (error) {
                toast(`保存标签失败：${error.message}`, "error");
            }
        };

        const openBook = async (book, autoResume = false) => {
            const aid = bookAid(book);
            if (!aid) {
                toast("这本书缺少书籍 ID", "error");
                return;
            }
            const shelfBook = findShelfBook(book);
            currentBook.value = {
                articleid: aid,
                articlename: bookName(book),
                author: bookAuthor(book),
                cover: bookCover(book),
                progress: book.progress || shelfBook?.progress || null,
                source_id: book.source_id || shelfBook?.source_id || "",
            };
            rememberBook(currentBook.value);
            loading.value = true;
            loadingText.value = "加载目录";
            try {
                const params = new URLSearchParams();
                if (currentBook.value.source_id) params.set("source", currentBook.value.source_id);
                const url = `/api/reader/chapters/${encodeURIComponent(currentBook.value.articleid)}${params.toString() ? "?" + params : ""}`;
                const json = await fetchJson(url);
                chapters.value = json.data || [];
                const progress = currentBook.value.progress;
                if (autoResume && progress?.chapterid) {
                    const index = chapters.value.findIndex(ch => String(ch.chapterid) === String(progress.chapterid));
                    if (index >= 0) {
                        await readChapter(chapters.value[index], index);
                        return;
                    }
                }
                setView("chapters");
            } catch (error) {
                toast(`加载目录失败：${error.message}`, "error");
            } finally {
                loading.value = false;
            }
        };

        const saveProgress = async (chapter, index) => {
            const aid = currentBook.value?.articleid;
            if (!aid) return;
            const progress = {
                chapterid: String(chapter.chapterid),
                chaptername: chapter.chaptername || "",
                index,
            };
            currentBook.value.progress = progress;
            localStorage.setItem(`readerProgress:${aid}`, JSON.stringify(progress));
            updateRecentProgress(aid, progress);
            try {
                await fetchJson(`/api/bookshelf/progress/${encodeURIComponent(aid)}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(progress),
                });
                await loadShelf();
            } catch (error) {
                console.error(error);
            }
        };

        const readChapter = async (chapter, index = -1) => {
            if (!chapter || !currentBook.value) return;
            const actualIndex = index >= 0
                ? index
                : chapters.value.findIndex(ch => String(ch.chapterid) === String(chapter.chapterid));
            loading.value = true;
            loadingText.value = "加载正文";
            currentChapterTitle.value = chapter.chaptername;
            try {
                const params = new URLSearchParams();
                if (currentBook.value.source_id) params.set("source", currentBook.value.source_id);
                const url = `/api/reader/content/${encodeURIComponent(currentBook.value.articleid)}/${encodeURIComponent(chapter.chapterid)}${params.toString() ? "?" + params : ""}`;
                const json = await fetchJson(url);
                const content = json.data?.content || "";
                currentContent.value = content.split("\n")
                    .filter(p => p.trim() !== "")
                    .map(p => `<p>${p.trim()}</p>`)
                    .join("");
                currentChapterIndex.value = actualIndex;
                contentIsCached.value = Boolean(json.cached);
                await saveProgress(chapter, actualIndex);
                setView("read");
                nextTick(() => scrollPane.value?.scrollTo(0, 0));
            } catch (error) {
                toast(`加载正文失败：${error.message}`, "error");
            } finally {
                loading.value = false;
            }
        };

        const goChapter = (offset) => {
            const nextIndex = currentChapterIndex.value + offset;
            if (nextIndex < 0 || nextIndex >= chapters.value.length) {
                toast(offset < 0 ? "已经是第一章" : "已经是最后一章", "error");
                return;
            }
            readChapter(chapters.value[nextIndex], nextIndex);
        };

        const handleReaderClick = (event) => {
            if (event.target.closest("button") || event.target.closest("a")) return;
            const rect = event.currentTarget.getBoundingClientRect();
            const ratio = (event.clientX - rect.left) / rect.width;
            if (ratio < 0.28) goChapter(-1);
            if (ratio > 0.72) goChapter(1);
        };

        const cacheBook = async (book) => {
            const aid = bookAid(book);
            if (!aid) return;
            cachingAid.value = aid;
            cacheProgress.value = { current: 0, total: 0 };
            try {
                const params = new URLSearchParams();
                if (book.source_id) params.set("source", book.source_id);
                const url = `/api/reader/cache/${encodeURIComponent(aid)}${params.toString() ? "?" + params : ""}`;
                const res = await fetch(url, { method: "POST" });
                if (!res.ok) throw new Error(`${res.status}`);
                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";
                let result = null;
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n");
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (!line.startsWith("data: ")) continue;
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.done) {
                                result = data;
                            } else {
                                cacheProgress.value = { current: data.current, total: data.total };
                            }
                        } catch (error) {}
                    }
                }
                await loadShelf();
                toast(result?.msg || "缓存完成");
            } catch (error) {
                toast(`缓存失败：${error.message}`, "error");
            } finally {
                cachingAid.value = "";
                cacheProgress.value = { current: 0, total: 0 };
            }
        };

        const fileNameFromDisposition = (header, fallback) => {
            if (!header) return fallback;
            const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
            if (encoded?.[1]) {
                try { return decodeURIComponent(encoded[1]); } catch (error) {}
            }
            const plain = header.match(/filename="?([^"]+)"?/i);
            return plain?.[1] || fallback;
        };

        const downloadBook = async (book, format) => {
            const aid = bookAid(book);
            if (!aid) return;
            const normalizedFormat = format === "ebup" ? "epub" : format;
            const key = `${aid}:${normalizedFormat}`;
            downloadingKey.value = key;
            try {
                const params = new URLSearchParams({ name: bookName(book), author: bookAuthor(book) });
                if (book.source_id) params.set("source", book.source_id);
                const res = await fetch(`/api/reader/download/${normalizedFormat}/${encodeURIComponent(aid)}?${params.toString()}`);
                if (!res.ok) {
                    let detail = `${res.status}`;
                    try {
                        const body = await res.json();
                        detail = body.detail || body.msg || detail;
                    } catch (error) {}
                    throw new Error(detail);
                }
                const blob = await res.blob();
                const filename = fileNameFromDisposition(res.headers.get("Content-Disposition"), `${bookName(book) || aid}.${normalizedFormat}`);
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
                toast("下载已开始");
            } catch (error) {
                toast(`下载失败：${error.message}`, "error");
            } finally {
                downloadingKey.value = "";
            }
        };

        const loadSources = async () => {
            try {
                sourcesList.value = await fetchJson("/api/sources/");
            } catch (error) {
                sourcesList.value = [];
                toast(`书源加载失败：${error.message}`, "error");
            }
        };

        const openSources = async () => {
            setView("sources");
            loading.value = true;
            loadingText.value = "加载书源";
            await loadSources();
            loading.value = false;
        };

        const resetSourceForm = () => {
            sourceForm.value = {
                name: "",
                base_url: "",
                color: "#4F46E5",
                search_path: "/api/novel/search?q={query}&page={page}&limit=20&lang=zh-CN",
                chapter_list_path: "/api/chapter/list/{aid}?lang=zh-CN",
                chapter_content_path: "/api/chapter/content/{aid}/{cid}?lang=zh-CN",
                field_map: { name: "articlename", author: "author", aid: "articleid", cover: "cover", intro: "intro" },
            };
        };

        const editSource = (src) => {
            editingSource.value = src;
            sourceForm.value = {
                name: src.name || "",
                base_url: src.base_url || "",
                color: src.color || "#4F46E5",
                search_path: src.search_path || "",
                chapter_list_path: src.chapter_list_path || "",
                chapter_content_path: src.chapter_content_path || "",
                field_map: {
                    name: (src.field_map || {}).name || "articlename",
                    author: (src.field_map || {}).author || "author",
                    aid: (src.field_map || {}).aid || "articleid",
                    cover: (src.field_map || {}).cover || "cover",
                    intro: (src.field_map || {}).intro || "intro",
                },
            };
            showSourceForm.value = true;
        };

        const saveSource = async () => {
            const form = sourceForm.value;
            if (!form.name.trim() || !form.base_url.trim()) {
                toast("名称和 Base URL 不能为空", "error");
                return;
            }
            try {
                if (editingSource.value) {
                    await fetchJson(`/api/sources/${editingSource.value.id}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(form),
                    });
                } else {
                    await fetchJson("/api/sources/", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(form),
                    });
                }
                showSourceForm.value = false;
                await loadSources();
                toast("书源已保存");
            } catch (error) {
                toast(`保存失败：${error.message}`, "error");
            }
        };

        const deleteSource = async (src) => {
            if (!confirm(`确认删除书源「${src.name}」？`)) return;
            try {
                await fetchJson(`/api/sources/${src.id}`, { method: "DELETE" });
                await loadSources();
                toast("书源已删除");
            } catch (error) {
                toast(`删除失败：${error.message}`, "error");
            }
        };

        const toggleSource = async (src) => {
            try {
                await fetchJson(`/api/sources/${src.id}/toggle`, { method: "POST" });
                await loadSources();
                toast(src.enabled !== false ? "书源已停用" : "书源已启用");
            } catch (error) {
                toast(`操作失败：${error.message}`, "error");
            }
        };

        onMounted(async () => {
            await Promise.all([loadShelf(), loadSources()]);
        });

        return {
            view,
            keyword,
            books,
            shelf,
            suggestions,
            showSuggestions,
            hasSearched,
            selectedSourceFilter,
            selectedBook,
            selectedBookProgress,
            chapters,
            currentContent,
            currentBook,
            currentChapterTitle,
            currentChapterIndex,
            contentIsCached,
            fontSize,
            theme,
            themes,
            loading,
            loadingText,
            activeTag,
            allTags,
            filteredShelf,
            filteredBooks,
            enabledSourceCount,
            cachedBookCount,
            recentDisplayBooks,
            quickTerms,
            searchHistory,
            editingTagsAid,
            tagDraft,
            cachingAid,
            cacheProgress,
            cachePercent,
            downloadingKey,
            scrollPane,
            sourcesList,
            showSourceForm,
            editingSource,
            sourceForm,
            toasts,
            readerThemeClass,
            navClass,
            filterClass,
            setView,
            setTheme,
            icon,
            getCover,
            bookAid,
            bookName,
            bookAuthor,
            bookCover,
            getSourceName,
            getSourceColor,
            sourceResultCount,
            doSearch,
            fetchSuggestions,
            chooseSuggestion,
            searchTerm,
            clearSearchHistory,
            openBookDetails,
            closeBookDetails,
            startSelectedBook,
            loadShelf,
            openShelf,
            addToShelf,
            removeFromShelf,
            checkUpdates,
            clearBookCache,
            clearAllCache,
            startTagEdit,
            saveTags,
            openBook,
            readChapter,
            goChapter,
            handleReaderClick,
            cacheBook,
            downloadBook,
            loadSources,
            openSources,
            resetSourceForm,
            editSource,
            saveSource,
            deleteSource,
            toggleSource,
        };
    },
}).mount("#app");
