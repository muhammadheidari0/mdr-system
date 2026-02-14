// @ts-nocheck
/**
 * Smart Document Search Component
 */
class DocSearch {
    constructor(inputId, onSelectCallback = null) {
        this.input = document.getElementById(inputId);
        this.callback = onSelectCallback;
        this.timer = null;

        if (!this.input) {
            console.warn(`DocSearch: Input element with ID '${inputId}' not found.`);
            return;
        }

        this.createDropdown();

        this.input.addEventListener("input", () => this.handleInput());
        this.input.addEventListener("focus", () => this.handleInput());

        document.addEventListener("click", (event) => {
            if (event.target !== this.input && !this.dropdown.contains(event.target)) {
                this.close();
            }
        });
    }

    createDropdown() {
        const parent = this.input.parentNode;
        if (getComputedStyle(parent).position === "static") {
            parent.style.position = "relative";
        }

        this.dropdown = document.createElement("div");
        this.dropdown.className = "ds-dropdown";
        parent.appendChild(this.dropdown);
    }

    handleInput() {
        const term = this.input.value.trim();
        clearTimeout(this.timer);

        if (term.length < 2) {
            this.close();
            return;
        }

        this.timer = setTimeout(() => this.search(term), 400);
    }

    async search(term) {
        this.dropdown.innerHTML = '<div class="ds-loading">Searching...</div>';
        this.dropdown.style.display = "block";

        try {
            const params = new URLSearchParams({
                doc: term,
                size: "7",
            });
            const url = `/api/v1/mdr/search?${params.toString()}`;

            let res;
            if (typeof window.fetchWithAuth === "function") {
                res = await window.fetchWithAuth(url);
            } else {
                const token = localStorage.getItem("access_token");
                const headers = token ? { Authorization: `Bearer ${token}` } : {};
                res = await fetch(url, { headers });
            }

            if (!res || !res.ok) {
                throw new Error(`Search request failed: ${res ? res.status : "no response"}`);
            }

            const data = await res.json();
            this.dropdown.innerHTML = "";

            if (data.items && data.items.length > 0) {
                data.items.forEach((doc) => {
                    const div = document.createElement("div");
                    div.className = "ds-item";

                    const title = doc.doc_title_p || doc.doc_title_e || "No Title";

                    const titleEl = document.createElement("span");
                    titleEl.className = "ds-title";
                    titleEl.title = title;
                    titleEl.textContent = title;

                    const codeEl = document.createElement("span");
                    codeEl.className = "ds-code";
                    codeEl.textContent = doc.doc_number || "-";

                    div.appendChild(titleEl);
                    div.appendChild(codeEl);
                    div.onclick = () => this.selectItem(doc);
                    this.dropdown.appendChild(div);
                });
            } else {
                this.dropdown.innerHTML = '<div class="ds-loading">No results found.</div>';
            }
        } catch (error) {
            console.error(error);
            this.dropdown.innerHTML = '<div class="ds-loading" style="color:#ef4444">Error fetching data</div>';
        }
    }

    selectItem(doc) {
        this.input.value = doc.doc_number;
        this.close();
        if (this.callback) {
            this.callback(doc);
        }
    }

    close() {
        this.dropdown.style.display = "none";
    }
}

window.DocSearch = DocSearch;

