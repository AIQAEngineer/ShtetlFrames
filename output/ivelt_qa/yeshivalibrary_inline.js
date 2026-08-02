

        /* POCZĄTEK KODU WZORCOWEGO - NIEZMIENIONY ANI JEDEN ZNAK LOGIKI */

        let rawRows = [];

        let colLabels = [];

        let activeFilters = { city: new Set(), author: new Set(), printer: new Set(), loc: new Set(), subject: new Set(), collection: new Set() };

        let sheetId = '1N--MCZSwjbLchUT37i-Ph5TwHoMxqNXUsO_zPngtokg';

        let url = `https://docs.google.com/spreadsheets/d/${sheetId}/gviz/tq?tqx=out:json`;

        let fuse;

        let isInitialLoad = true;

        let currentShelfLanguage = 'PL'; // Globalna zmienna sterująca językiem półki



        function extractYear(s) { if (!s || s === "---") return 0; let match = String(s).match(/\d{4}/); return match ? parseInt(match[0]) : 0; }

        function hebrewYearToNumber(s) { 

            if (!s || s === "---") return 999999; 

            let c = String(s).replace(/[\\\"\'\.\s\(\)\[\]]/g, "").trim(); 

            let v = {'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'כ':20,'ך':20,'ל':30,'מ':40,'ם':40,'נ':50,'ן':50,'ס':60,'ע':70,'פ':80,'ף':80,'צ':90,'ץ':90,'ק':100,'ר':200,'ש':300,'ת':400}; 

            let sum = 0; let cleanC = c.match(/[\u0590-\u05FF]/g);

            if (cleanC) { for (let i=0; i < cleanC.length; i++) sum += v[cleanC[i]] || 0; }

            if (sum > 0 && sum < 1000) sum += 5000; return sum || 999999; 

        }

        function numberToHebrewYear(num) {

            let n = parseInt(num); if (n > 5000) n -= 5000;

            let heb = ""; vArr = [400,300,200,100,90,80,70,60,50,40,30,20,10,9,8,7,6,5,4,3,2,1], lArr = ['ת','ש','ר','ק','צ','פ','ע','ס','נ','מ','ל','כ','י','ט','ח','ז','ו','ה','ד','ג','ב','א'];

            for(let i=0; i<vArr.length; i++) { while(n >= vArr[i]) { heb += lArr[i]; n -= vArr[i]; } }

            return heb;

        }

async function init() {

    try {

        let r = await fetch(url);

        let t = await r.text();

        let json = JSON.parse(t.substring(t.indexOf("{"), t.lastIndexOf("}") + 1));

        rawRows = json.table.rows;

        colLabels = json.table.cols;



        // DODANO: Zapisanie danych do zmiennej globalnej dla przycisku "Generuj"

        window.currentData = rawRows; 



        const fuseData = rawRows.map(row => ({ 

            original: row, 

            searchable: row.c.map(cell => getVal(cell)).join(' ') 

        }));

        fuse = new Fuse(fuseData, { keys: ['searchable'], threshold: 0.3, ignoreLocation: true });



        applyURLState();

        filterAndSort();



        // DODANO: Pierwsze uruchomienie grafu (domyślnie autorzy)

        renderNetworkGraph(rawRows, 'author'); 



        document.getElementById('loader').style.display = 'none';

        window.addEventListener('popstate', () => { applyURLState(); filterAndSort(false); });

    } catch (e) { 

        console.error(e); 

    }

}



        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }

        function getVal(cell) { return cell && (cell.f || (cell.v !== null ? String(cell.v) : "")) || ""; }

        function isUnknown(val) { let v = val ? val.trim() : ""; return !v || v === "---" || v === "-"; }

        function updateYearLabel(val) { document.getElementById('yearVal').innerText = val; }

        function updateHebYearLabel(val) { document.getElementById('hebYearVal').innerText = numberToHebrewYear(val); }

        function toggleKeyboard() { let k = document.getElementById('keyboard'); k.style.display = k.style.display === 'grid' ? 'none' : 'grid'; }

        function addChar(c) { document.getElementById('search').value += c; filterAndSort(); }

        function delChar() { let s = document.getElementById('search'); s.value = s.value.slice(0,-1); filterAndSort(); }



        function filterFacetList(input, listId) {

            let filter = input.value.toLowerCase();

            let items = document.querySelectorAll(`#${listId} li`);

            items.forEach(li => {

                let span = li.querySelector('span');

                if (span) {

                    let txt = span.innerText.toLowerCase();

                    li.style.display = txt.includes(filter) ? "flex" : "none";

                }

            });

        }



function clearFacet(type) {

            if (type === 'all') { 

                activeFilters.city.clear();

                activeFilters.author.clear(); activeFilters.printer.clear(); activeFilters.loc.clear(); activeFilters.subject.clear(); 

                activeFilters.collection.clear(); // <-- DODANO POPRAWNIE

                document.getElementById('yearSlider').value = 1939;

                document.getElementById('hebYearSlider').value = 5700;

                updateYearLabel(1939); updateHebYearLabel(5700);

                document.getElementById('search').value = "";

            } else activeFilters[type].clear();

            filterAndSort();

        }



        function toggleFilter(val, type) {

            if (activeFilters[type].has(val)) activeFilters[type].delete(val);

            else activeFilters[type].add(val);

            filterAndSort();

        }



function filterAndSort(updateURL = true) {

            const term = document.getElementById('search').value.toLowerCase().trim();

            const maxYear = parseInt(document.getElementById('yearSlider').value);

            const maxHebYear = parseInt(document.getElementById('hebYearSlider').value);

            const sPL = document.getElementById('sortSelectPL').value;

            const sHE = document.getElementById('sortSelectHE').value;



            let searchFiltered = (term && fuse) ? fuse.search(term).map(r => r.item.original) : rawRows;

            const filtered = searchFiltered.filter(r => {

                // 1. Pobranie wartości z kolumn

                const cityPL = getVal(r.c[7]), 

                      authPL = getVal(r.c[3]), 

                      prnPL = getVal(r.c[10]), 

                      locPL = getVal(r.c[11]),

                      subjPL = getVal(r.c[31]);



                const year = extractYear(getVal(r.c[5])), 

                      hebYear = hebrewYearToNumber(getVal(r.c[6]));



                // 2. Definicja dopasowań

                const matchYear = (year === 0 || year <= maxYear) && (hebYear === 999999 || hebYear <= maxHebYear);

                const matchCity = activeFilters.city.size === 0 || (isUnknown(cityPL) ? activeFilters.city.has('_UNK_') : activeFilters.city.has(cityPL.trim()));

                const matchAuth = activeFilters.author.size === 0 || (isUnknown(authPL) ? activeFilters.author.has('_UNK_') : activeFilters.author.has(authPL.trim()));

                const matchPrn = activeFilters.printer.size === 0 || (isUnknown(prnPL) ? activeFilters.printer.has('_UNK_') : activeFilters.printer.has(prnPL.trim()));

                const matchLoc = activeFilters.loc.size === 0 || (isUnknown(locPL) ? activeFilters.loc.has('_UNK_') : activeFilters.loc.has(locPL.trim()));

                

                // 3. Logika dopasowania hasła przedmiotowego (Oczyszczone z duplikatu!)

                const matchSubj = activeFilters.subject.size === 0 || 

                    Array.from(activeFilters.subject).some(s => {

                        if (s === '_UNK_') return isUnknown(subjPL);

                        return subjPL.split(';').map(p => p.trim()).includes(s);

                    });



                // 4. NOWOŚĆ: Logika dopasowania pod kątem nowej fasetki Kolekcje

                let matchCollection = true;

                if (activeFilters.collection && activeFilters.collection.size > 0) {

                    matchCollection = false;

                    

                    const collectionColumnsMap = [

                        { name: "Majer Szapira", index: 29 },          // AD

                        { name: "Icchak Ajzik Pinaj", index: 33 },     // AH

                        { name: "Książnica im. Chafec Chajima", index: 34 }, // AI

                        { name: "Manes Gold", index: 35 },             // AJ

                        { name: "Arje Cwi Frumer", index: 36 }          // AK

                    ];



                    collectionColumnsMap.forEach(col => {

                        if (activeFilters.collection.has(col.name)) {

                            let cellVal = getVal(r.c[col.index]).trim().toLowerCase();

                            if (cellVal === 'x') {

                                matchCollection = true;

                            }

                        }

                    });

                }



                // Zwrócenie wyniku (Uwzględnia nowy filtr na samym końcu)

                return matchYear && matchCity && matchAuth && matchPrn && matchLoc && matchSubj && matchCollection;

            });



            const sortVal = sPL !== "none" ? sPL : sHE;

            if(sortVal !== "none") {

                filtered.sort((a, b) => {

                    const norm = (s) => getVal(s).replace(/[\[\]]/g, "").toLowerCase().trim();

                    if (sortVal.includes("year")) {

                        let vA = extractYear(getVal(a.c[5])), vB = extractYear(getVal(b.c[5]));

                        if (sortVal.includes("_he")) { vA = hebrewYearToNumber(getVal(a.c[6])); vB = hebrewYearToNumber(getVal(b.c[6])); }

                        if (vA === 0 || vA === 999999) return 1; if (vB === 0 || vB === 999999) return -1;

                        return sortVal.includes("desc") ? vB - vA : vA - vB;

                    }

                    let i = 1;

                    if (sortVal === 'title_he') i = 2;

                    else if (sortVal === 'author') i = 3;

                    else if (sortVal === 'author_he') i = 4;

                    let valA = norm(a.c[i]), valB = norm(b.c[i]);

                    const isAUnknown = isUnknown(valA), isBUnknown = isUnknown(valB);

                    if (isAUnknown && !isBUnknown) return 1;

                    if (!isAUnknown && isBUnknown) return -1;

                    return valA.localeCompare(valB, sortVal.includes('_he') ? 'he' : 'pl');

                });

            }



            updateFacetsUI(term, maxYear, maxHebYear);

            render(filtered);

            if (updateURL) syncStateToURL();

            if (isInitialLoad) {

                const urlParams = new URLSearchParams(window.location.search);

                if (urlParams.has('id')) openModal(urlParams.get('id'));

                isInitialLoad = false;

            }

        }



        function updateFacetsUI(term, maxYear, maxHebYear) {

            // 1. Inicjalizacja liczników (Dodano collection: {})

            const counts = { city: {}, author: {}, printer: {}, loc: {}, subject: {}, collection: {} };

            const plToHe = { city: {}, author: {} };

            let searchFiltered = (term && fuse) ? fuse.search(term).map(r => r.item.original) : rawRows;



            const collectionColumnsMap = [

                { name: "Majer Szapira", index: 29 },          // AD

                { name: "Icchak Ajzik Pinaj", index: 33 },     // AH

                { name: "Książnica im. Chafec Chajima", index: 34 }, // AI

                { name: "Manes Gold", index: 35 },             // AJ

                { name: "Arje Cwi Frumer", index: 36 }          // AK

            ];



            searchFiltered.forEach(r => {

                // 2. Pobranie wartości

                const cityPL = getVal(r.c[7]), authPL = getVal(r.c[3]), prnPL = getVal(r.c[10]), locPL = getVal(r.c[11]);

                const subjPL = getVal(r.c[31]); 

                const cityHE = getVal(r.c[22]) || cityPL, authHE = getVal(r.c[4]) || authPL;

                

                const year = extractYear(getVal(r.c[5])), hebYear = hebrewYearToNumber(getVal(r.c[6]));

                

                // Filtracja lat

                if (!((year === 0 || year <= maxYear) && (hebYear === 999999 || hebYear <= maxHebYear))) return;



                // 3. Logika dopasowania tematu

                const matchSubjCond = (activeFilters.subject.size === 0 || 

                    Array.from(activeFilters.subject).some(s => {

                        if (s === '_UNK_') return isUnknown(subjPL);

                        return subjPL.split(';').map(p => p.trim()).includes(s);

                    })

                );



                // Globalna filtracja pod kątem wybranej kolekcji (by inne fasetki reagowały na wybór kolekcji)

                let matchCollectionCond = true;

                if (activeFilters.collection && activeFilters.collection.size > 0) {

                    matchCollectionCond = false;

                    collectionColumnsMap.forEach(col => {

                        if (activeFilters.collection.has(col.name)) {

                            if (getVal(r.c[col.index]).trim().toLowerCase() === 'x') {

                                matchCollectionCond = true;

                            }

                        }

                    });

                }



                // 4. Warunki "Pass" dla każdej kategorii (Uwzględniają nowy filtr kolekcji)

                const passCity = (activeFilters.author.size === 0 || activeFilters.author.has(isUnknown(authPL)?'_UNK_':authPL.trim())) && 

                                 (activeFilters.printer.size === 0 || activeFilters.printer.has(isUnknown(prnPL)?'_UNK_':prnPL.trim())) && 

                                 (activeFilters.loc.size === 0 || activeFilters.loc.has(isUnknown(locPL)?'_UNK_':locPL.trim())) && 

                                 matchSubjCond && matchCollectionCond;



                const passAuth = (activeFilters.city.size === 0 || activeFilters.city.has(isUnknown(cityPL)?'_UNK_':cityPL.trim())) && 

                                 (activeFilters.printer.size === 0 || activeFilters.printer.has(isUnknown(prnPL)?'_UNK_':prnPL.trim())) && 

                                 (activeFilters.loc.size === 0 || activeFilters.loc.has(isUnknown(locPL)?'_UNK_':locPL.trim())) && 

                                 matchSubjCond && matchCollectionCond;



                const passPrn = (activeFilters.city.size === 0 || activeFilters.city.has(isUnknown(cityPL)?'_UNK_':cityPL.trim())) && 

                                (activeFilters.author.size === 0 || activeFilters.author.has(isUnknown(authPL)?'_UNK_':authPL.trim())) && 

                                (activeFilters.loc.size === 0 || activeFilters.loc.has(isUnknown(locPL)?'_UNK_':locPL.trim())) && 

                                matchSubjCond && matchCollectionCond;



                const passLoc = (activeFilters.city.size === 0 || activeFilters.city.has(isUnknown(cityPL)?'_UNK_':cityPL.trim())) && 

                                (activeFilters.author.size === 0 || activeFilters.author.has(isUnknown(authPL)?'_UNK_':authPL.trim())) && 

                                (activeFilters.printer.size === 0 || activeFilters.printer.has(isUnknown(prnPL)?'_UNK_':prnPL.trim())) && 

                                matchSubjCond && matchCollectionCond;



                const passSubj = (activeFilters.city.size === 0 || activeFilters.city.has(isUnknown(cityPL)?'_UNK_':cityPL.trim())) && 

                                 (activeFilters.author.size === 0 || activeFilters.author.has(isUnknown(authPL)?'_UNK_':authPL.trim())) && 

                                 (activeFilters.printer.size === 0 || activeFilters.printer.has(isUnknown(prnPL)?'_UNK_':prnPL.trim())) && 

                                 (activeFilters.loc.size === 0 || activeFilters.loc.has(isUnknown(locPL)?'_UNK_':locPL.trim())) &&

                                 matchCollectionCond;



                // Warunek pass dla samej kolekcji (nie może odcinać samej siebie, by pokazywać inne opcje kolekcji)

                const passColl = (activeFilters.city.size === 0 || activeFilters.city.has(isUnknown(cityPL)?'_UNK_':cityPL.trim())) && 

                                 (activeFilters.author.size === 0 || activeFilters.author.has(isUnknown(authPL)?'_UNK_':authPL.trim())) && 

                                 (activeFilters.printer.size === 0 || activeFilters.printer.has(isUnknown(prnPL)?'_UNK_':prnPL.trim())) && 

                                 (activeFilters.loc.size === 0 || activeFilters.loc.has(isUnknown(locPL)?'_UNK_':locPL.trim())) &&

                                 matchSubjCond;



                // 5. Zliczanie wartości standardowych

                if (passCity) { let k = isUnknown(cityPL)?'_UNK_':cityPL.trim(); counts.city[k] = (counts.city[k]||0)+1; plToHe.city[k] = isUnknown(cityPL)?'לא ידוע':cityHE.trim(); }

                if (passAuth) { let k = isUnknown(authPL)?'_UNK_':authPL.trim(); counts.author[k] = (counts.author[k]||0)+1; plToHe.author[k] = isUnknown(authPL)?'לא ידוע':authHE.trim(); }

                if (passPrn) { let k = isUnknown(prnPL)?'_UNK_':prnPL.trim(); counts.printer[k] = (counts.printer[k]||0)+1; }

                if (passLoc) { let k = isUnknown(locPL)?'_UNK_':locPL.trim(); counts.loc[k] = (counts.loc[k]||0)+1; }

                

                if (passSubj) { 

                    if (isUnknown(subjPL)) {

                        counts.subject['_UNK_'] = (counts.subject['_UNK_'] || 0) + 1;

                    } else {

                        subjPL.split(';').forEach(part => {

                            let k = part.trim();

                            if (k) counts.subject[k] = (counts.subject[k] || 0) + 1;

                        });

                    }

                }



                // Zliczanie dynamiczne "x" dla Kolekcji

                if (passColl) {

                    collectionColumnsMap.forEach(col => {

                        let val = getVal(r.c[col.index]).trim().toLowerCase();

                        if (val === 'x') {

                            counts.collection[col.name] = (counts.collection[col.name] || 0) + 1;

                        }

                    });

                }

            });



            // --- RENDEROWANIE INTERFEJSU DLA KOLEKCJI ---

            const collectionListUL = document.getElementById('collectionListPL');

            if (collectionListUL) {

                const allCollectionNames = ["Arje Cwi Frumer", "Icchak Ajzik Pinaj", "Książnica im. Chafec Chajima", "Majer Szapira", "Manes Gold"];

                allCollectionNames.forEach(name => {

                    if (!counts.collection[name]) counts.collection[name] = 0;

                });

                // Wywołanie Twojej uniwersalnej funkcji generującej strukturę faset (zintegrowane)

                renderFacetList('collectionListPL', counts.collection, 'collection', false, 'Wszystkie / All', 'Nieznane / Unknown', {});

            }



            // --- REGENEROWANIE POZOSTAŁYCH HISTORII FILTRÓW ---

            renderFacetList('cityListPL', counts.city, 'city', false, 'Wszystko/ All', 'Nieznane', null);

            renderFacetList('authorListPL', counts.author, 'author', false, 'Wszystko/ All', 'Nieznany', null);

            renderFacetList('printerListPL', counts.printer, 'printer', false, 'Wszystko/ All', 'Nieznany', null);

            renderFacetList('locListPL', counts.loc, 'loc', false, 'Wszystko/ All', 'Nieznana', null);

            renderFacetList('subjectListPL', counts.subject, 'subject', false, 'Wszystko/ All', 'Nieznane', null);

            

            const cityListHE = document.getElementById('cityListHE');

            if (cityListHE) renderFacetList('cityListHE', counts.city, 'city', true, 'הכל', 'לא ידוע', plToHe.city);

            

            const authorListHE = document.getElementById('authorListHE');

            if (authorListHE) renderFacetList('authorListHE', counts.author, 'author', true, 'הכל', 'לא ידוע', plToHe.author);



            // Dynamiczna aktualizacja plakietek (badge) przy nagłówkach

            Object.keys(activeFilters).forEach(t => { 

                let b = document.querySelector(`#det-${t} .active-badge`); 

                if(b) { 

                    b.innerText = activeFilters[t].size; 

                    b.style.display = activeFilters[t].size > 0 ? 'inline' : 'none'; 

                } 

            });

        }



function renderFacetList(id, counts, type, isHeb, allLabel, unkLabel, heMap) {

            const list = document.getElementById(id);

            if (!list) return; // <-- DODANE ZABEZPIECZENIE

            let html = `<li class="facet-item ${activeFilters[type].size===0?'active':''}" onclick="clearFacet('${type}')">${allLabel}</li>`;

            Object.keys(counts).sort((a,b) => (isHeb?heMap[a]:a).localeCompare(isHeb?heMap[b]:b, isHeb?'he':'pl')).forEach(k => {

                if(k==='_UNK_') return;

                html += `<li class="facet-item ${activeFilters[type].has(k)?'active':''}" onclick="toggleFilter('${k}', '${type}')"><span>${isHeb?heMap[k]:k}</span><span class="count-pill">${counts[k]}</span></li>`;

            });

            if (counts['_UNK_']) html += `<li class="facet-item ${activeFilters[type].has('_UNK_')?'active':''}" onclick="toggleFilter('_UNK_', '${type}')"><span>${unkLabel}</span><span class="count-pill">${counts['_UNK_']}</span></li>`;

            list.innerHTML = html;

        }



function render(rows) {

            const container = document.getElementById('container');

            container.innerHTML = rows.map(r => `

                <article class="item-card" onclick="openModal('${r.c[0].v}')" style="display: flex; flex-direction: column;">

                    <div class="item-content">

                        <div class="row-flex">

                            <!-- Zmiana span na h2 jako kluczowe nagłówki dla wyszukiwarki -->

                            <h2 class="title-pl" style="margin: 0; font-size: 17px; font-weight: bold; text-transform: uppercase; flex: 1;">${getVal(r.c[1])}</h2>

                            <h2 class="title-heb" style="margin: 0; font-size: 19px; color: #1a1a1a; text-align: right; direction: rtl; flex: 1; font-family: 'SBL Hebrew', serif;">${getVal(r.c[2])}</h2>

                        </div>

                        <div class="author-row">

                            <div class="column-pl">

                                <strong style="font-weight: 600;">${getVal(r.c[3])}</strong>

                                <span style="font-size:12px;color:#888">${getVal(r.c[7])}, ${getVal(r.c[5])}</span>

                            </div>

                            <div class="column-he">

                                <strong style="font-weight: 600; font-family: 'SBL Hebrew', serif;">${getVal(r.c[4])}</strong>

                                <span style="font-size:13px;color:#888">${getVal(r.c[22]) || getVal(r.c[7])}, ${getVal(r.c[6])}</span>

                            </div>

                        </div>

                    </div>

                </article>`).join('');

// --- LOGIKA INTELIGENTNEGO LICZNIKA ---

    const searchVal = document.getElementById('search').value.trim();

    

    // Sprawdzamy, czy jakikolwiek filtr fasetowy jest aktywny

    const hasActiveFilters = Object.values(activeFilters).some(filterSet => filterSet.size > 0);



    // Sprawdzamy, czy suwaki lat są w pozycji domyślnej (1500-1939 / 5260-5700)

    // Jeśli suwaki są "rozwinięte" na max, uznajemy, że filtr lat nie jest aktywny

    const isYearFiltered = document.getElementById('yearSlider').value != 1939 || 

                           document.getElementById('hebYearSlider').value != 5700;



    if (searchVal === "" && !hasActiveFilters && !isYearFiltered) {

        // Jeśli nie ma szukania ani filtrów -> Pokaż CAŁĄ bazę (naprawia brakujące 3 sztuki)

        document.getElementById('inlineCounter').innerText = rawRows.length;

    } else {

        // Jeśli użytkownik coś filtruje -> Pokaż liczbę przefiltrowanych

        document.getElementById('inlineCounter').innerText = rows.length;

    }

            renderShelf(rows);

        }



        function copyLink(id) {

            const baseUrl = window.location.origin + window.location.pathname;

            const uniqueLink = `${baseUrl}?id=${id}`;

            navigator.clipboard.writeText(uniqueLink).then(() => {

                const btn = document.getElementById('copyBtn');

                btn.innerText = "SKOPIOWANO / COPIED";

                setTimeout(() => btn.innerText = "KOPIUJ / COPY", 2000);

            });

        }



function openModal(rowIndex) {

const topElement = document.querySelector('.modal-img-col');

    if (topElement) {

        topElement.scrollIntoView({ behavior: 'auto', block: 'start' });

    }

    // 1. Znalezienie danych wiersza

    if (!rawRows) return;

    const r = rawRows.find(row => row.c[0] && row.c[0].v == rowIndex);

    if (!r) return;



    // Funkcja pomocnicza do znalezienia tytułu po ID (bezpieczna)

    const getTitleById = (id) => {

        const foundRow = rawRows.find(row => row.c[0] && row.c[0].v == id);

        if (foundRow && foundRow.c[1]) return foundRow.c[1].v;

        return "ID " + id;

    };



    // --- PRZYGOTOWANIE SLIDERA ---

    const extraImagesRaw = (r.c[27] && r.c[27].v) ? String(r.c[27].v).trim() : "";

    let galleryHTML = "";

    currentSlide = 0; 



    if (extraImagesRaw && extraImagesRaw !== "-" && extraImagesRaw !== "") {

        const images = extraImagesRaw.split('|').map(url => url.trim()).filter(Boolean);

        if (images.length > 0) {

            galleryHTML = `

                <div class="photo-slider-container" data-current-slide="0">

                    ${images.length > 1 ? `

                        <button class="photo-slider-btn photo-prev-btn" onclick="moveSlide(-1, this)">&#10094;</button>

                        <button class="photo-slider-btn photo-next-btn" onclick="moveSlide(1, this)">&#10095;</button>

                    ` : ''}

                    <div class="photo-slider-wrapper">

                        ${images.map(imgUrl => `

                            <img src="${imgUrl}" onclick="openLightbox(this.src, true)" alt="Dodatkowe zdjęcie">

                        `).join('')}

                    </div>

                </div>

            `;

        }

    }



    const boundWithRaw = (r.c[26] && r.c[26].v) ? String(r.c[26].v).trim() : "";

    let h = ""; 

    let link = getVal(r.c[16]);

    let boundWithSection = "";



    // Pętla do 31 (bez 32, które obsłużymy osobno na końcu)

    for (let i = 0; i <= 31; i++) { 

        if (!colLabels[i]) continue;



        let labelName = colLabels[i].label ? colLabels[i].label.toLowerCase() : "";

        let val = getVal(r.c[i]);

        const isSignature = (i === 14);

        const isPrinter = (i === 10);



        // Wykluczenia

        if ([8, 17, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31].includes(i)) continue;

        if (labelName.includes("pełny opis") || labelName.includes("fotografie")) continue;



        if ((!val || val === "---" || val === "") && !isSignature && !isPrinter) continue;

        if (isSignature && (!val || val === "---" || val === "")) val = "-";

        if (isPrinter && (!val || val === "---" || val === "")) val = "Nieznany / Unknown";



        if (val.startsWith('http')) {

            h += `<div class="detail-box"><span class="label">${colLabels[i].label}</span><a href="${val}" target="_blank" class="link-btn">SZCZEGÓŁY / DETAILS</a></div>`;

        } else {

            h += `<div class="detail-box"><span class="label">${colLabels[i].label}</span><span>${val}</span></div>`;

            

            if (i === 7) {

                let hebrewPlace = getVal(r.c[22]);

                if (hebrewPlace && hebrewPlace !== "---" && hebrewPlace !== "-") {

                    h += `<div class="detail-box"><span class="label">מקום הוצאה (אחיד)</span><span style="direction: rtl; text-align: left; display: block;">${hebrewPlace}</span></div>`;

                }

            }



            if (i === 10) {

                let langVal = getVal(r.c[30]);

                if (langVal && langVal !== "---") h += `<div class="detail-box"><span class="label">Język / Language</span><span>${langVal}</span></div>`;

                let subjectVal = getVal(r.c[31]);

                if (subjectVal && subjectVal !== "---" && subjectVal !== "-" && subjectVal !== "") {

                    h += `<div class="detail-box"><span class="label">Hasła przedmiotowe / Subject headings</span><span style="font-style: italic; color: #444;">${subjectVal}</span></div>`;

                }

            }

            

            // Typ pieczątki pod Uwagami (indeks 11)

            if (i === 11) { 

                let stampVal = getVal(r.c[28]); 

                if (stampVal && stampVal !== "---") {

                    h += `

                    <div class="detail-box">

                        <span class="label" style="display: flex; align-items: center; gap: 6px;">

                            Typ pieczątki JChL / YChL Stamp Type

                            <a href="https://teatrnn.pl/wystawy/typologia-znakow-wlasnosciowych-jeszywas-chachmej-lublin/" 

                               target="_blank" 

                               title="Zobacz opis typologii / See typology description"

                               style="text-decoration: none; display: inline-flex;">

                               <span style="

                                    display: inline-block;

                                    width: 14px;

                                    height: 14px;

                                    background-color: #eee;

                                    color: #888;

                                    border-radius: 50%;

                                    text-align: center;

                                    font-size: 10px;

                                    line-height: 14px;

                                    font-family: sans-serif;

                                    cursor: help;

                                    transition: all 0.2s;

                                    border: 1px solid #ddd;

                               " onmouseover="this.style.backgroundColor='#c73848'; this.style.color='#fff';" 

                                 onmouseout="this.style.backgroundColor='#eee'; this.style.color='#888';">?</span>

                            </a>

                        </span>

                        <span>${stampVal}</span>

                    </div>`;

                }

            }

        }

    }



    // --- PRZYGOTOWANIE SEKCJI BHB (Kolumna AG) ---

    let bhbSection = "";

    let biblioVal = getVal(r.c[32]);

    if (biblioVal && biblioVal !== "" && biblioVal !== "---" && biblioVal !== "-") {

        const bhbUrl = `https://uli.nli.org.il/discovery/search?query=any,contains,${biblioVal}&tab=BHB_slot&search_scope=BHB&vid=972NNL_ULI_C:BHB&offset=0`;

        bhbSection = `

            <div class="detail-box">

                <span class="label">Bibliography of the Hebrew Book</span>

                <span>

                    <a href="${bhbUrl}" target="_blank" class="bound-with-link" style="color: #1a1a1a; text-decoration: none; display: block;">

                        ${biblioVal}

                    </a>

                </span>

            </div>`;

    }



    // --- PRZYGOTOWANIE SEKCJI WSPÓŁOPRAWNE ---

if (boundWithRaw && boundWithRaw !== "-" && boundWithRaw !== "0") {

    const boundIds = boundWithRaw.split(',').map(id => id.trim());

    const boundLinks = boundIds.map(id => {

        const bookTitle = getTitleById(id); 

        // ZMIANA: Zamiast <a href="..."> dajemy onclick, który wywoła funkcję bez przeładowania strony

        return `<a href="javascript:void(0)" 

                   onclick="openModal('${id}')" 

                   class="bound-with-link" 

                   style="color: #1a1a1a; text-decoration: none; display: block; margin-bottom: 5px;">

                   ${bookTitle}

                </a>`;

    }).join('');

    boundWithSection = `<div class="detail-box"><span class="label">Współoprawne / Bound with</span><span>${boundLinks}</span></div>`;

}



    // --- SKŁADANIE FINALNEGO HTML ---

    let finalDetailsHtml = h;

    const callNumberLabel = "Obecna Sygnatura / Current Call number"; 

    

    // Wstawienie współoprawnych pod sygnaturę

    if (boundWithSection) {

        const regex = new RegExp(`(<div class="detail-box">\\s*<span class="label">${callNumberLabel}</span>.*?</div>)`, 's');

        finalDetailsHtml = regex.test(h) ? h.replace(regex, `$1${boundWithSection}`) : h + boundWithSection;

    }



    // DODANIE BHB NA SAMYM KOŃCU DANYCH (ale przed przyciskiem KOPIUJ)

    finalDetailsHtml += bhbSection;



    // SEKCJA LINKU (zawsze na samym dole kolumny danych)

    const copySection = `<div class="detail-box"><span class="label">Link do rekordu / Link to record</span><button id="copyBtn" class="link-btn" onclick="copyLink('${rowIndex}')">KOPIUJ / COPY</button></div>`;

    

    const provenanceHTML = `<div id="provenance-container" style="display:none; margin-top:20px; border-top:1px solid #1a1a1a; padding-top:15px;"><span class="prov-label" style="font-weight:bold; font-size:12px;">MAPA PROWENIENCJI / PROVENANCE MAP</span><div id="provenance-graph-space" class="dynamic-graph-height"></div></div>`;



    const isMobile = window.innerWidth <= 768;

    document.getElementById('modalContent').innerHTML = `

        <div class="modal-body">

            <div class="modal-img-col">

                <img src="${getVal(r.c[23])}" onclick="openLightbox(this.src, false)" style="max-width:100%; cursor: zoom-in;">

                ${link ? `<a href="${link}" target="_blank" class="link-btn" style="margin-top:10px; display:block; text-align:center;">SZCZEGÓŁY / DETAILS</a>` : ''}

                <div class="gallery-desktop" style="display: ${isMobile ? 'none' : 'block'};">${galleryHTML}</div>

            </div>

            <div class="modal-data-col">

                ${finalDetailsHtml} 

                ${copySection}

                ${provenanceHTML}

                <div class="gallery-mobile" style="display: ${isMobile ? 'block' : 'none'}; margin-top: 20px;">${galleryHTML}</div>

            </div>

        </div>

    `;



    document.getElementById('modalOverlay').style.display = 'flex';

    const url = new URL(window.location); 

    url.searchParams.set('id', rowIndex); 

    window.history.replaceState({}, '', url);



    const provText = (r.c[24] && r.c[24].v) ? String(r.c[24].v).trim() : "";

    const provDetails = (r.c[25] && r.c[25].v) ? String(r.c[25].v).trim() : "";

    if (provText && provText !== "-") {

        document.getElementById('provenance-container').style.display = 'block';

        setTimeout(() => {

            if (typeof ProvenanceModule !== 'undefined') ProvenanceModule.init(provText, provDetails, 'provenance-graph-space');

        }, 300);

    }

}



        function closeModalManual() { document.getElementById('modalOverlay').style.display = 'none'; const url = new URL(window.location); url.searchParams.delete('id'); window.history.replaceState({}, '', url); }

        function closeModal(e) { if(e.target.id === 'modalOverlay') closeModalManual(); }

        function syncStateToURL() { const url = new URL(window.location); if (document.getElementById('search').value) url.searchParams.set('q', document.getElementById('search').value); else url.searchParams.delete('q'); window.history.replaceState({}, '', url); }

        function applyURLState() { const p = new URLSearchParams(window.location.search); if (p.has('q')) document.getElementById('search').value = p.get('q'); }

        function updateSort(l) { if(l === 'PL') document.getElementById('sortSelectHE').value = "none"; else document.getElementById('sortSelectPL').value = "none"; filterAndSort(); }



        /* KONIEC KODU WZORCOWEGO - LOGIKA DODATKOWA STATYSTYK */



        let mapInstance, timelineChart, locChart, stampsChart, szapiraChart, mapInitialized = false;

function switchTab(mode) {

    // 1. Aktualizacja klas przycisków

    document.querySelectorAll('.nav-tab-btn').forEach(b => b.classList.remove('active'));

    const targetBtn = document.getElementById(`tab-${mode}`);

    if (targetBtn) targetBtn.classList.add('active');



    // 2. Zamykanie sidebaru na mobile

    document.getElementById('sidebar').classList.remove('open');



    // 3. Zarządzanie widocznością kontenerów

    const catalogView = document.getElementById('container');

    const shelfView = document.getElementById('shelf-container');

    const statsView = document.getElementById('dashboard-view');



    // Resetowanie widoków

    catalogView.style.display = 'none';

    if (shelfView) shelfView.style.display = 'none';

    if (statsView) statsView.style.display = 'none';



    if (mode === 'stats') {

        document.body.classList.add('stats-mode');

        document.documentElement.classList.add('stats-mode');

        if (statsView) statsView.style.display = 'block';



        if (!mapInitialized) {

            const isMobile = window.innerWidth < 768;

            const mapOptions = isMobile ? { 

                dragging: true, touchZoom: true, tap: true, 

                scrollWheelZoom: false, bounceAtZoomLimits: true 

            } : {};



            mapInstance = L.map('map-container', mapOptions).setView([50, 20], 4);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OSM' }).addTo(mapInstance);



            if (isMobile) {

                mapInstance.on('focus', () => { mapInstance.scrollWheelZoom.enable(); });

            }

            mapInitialized = true;

        }

        setTimeout(() => { 

            renderStats(); 

            if (mapInstance) mapInstance.invalidateSize(); 

        }, 300);



    } else if (mode === 'shelf') {

        document.body.classList.remove('stats-mode');

        document.documentElement.classList.remove('stats-mode');

        if (shelfView) shelfView.style.display = 'block';

        window.scrollTo(0,0);

        filterAndSort(); // Odświeża zawartość półki przy przełączaniu



    } else { // tryb 'catalog'

        document.body.classList.remove('stats-mode');

        document.documentElement.classList.remove('stats-mode');

        catalogView.style.display = 'block';

        window.scrollTo(0,0);

        filterAndSort();

    }

}

function renderShelf(rows) {

    const shelfContent = document.getElementById('shelf-content');

    if (!shelfContent) return;



    const defaultUrl = "https://teatrnn.pl/cache/local/image/1280x1024/websites/wystawy/Jesziwa/teatrnn.jpeg/";



    // Sprawdzamy kierunek: jeśli hebrajski, dodajemy klasę zmieniającą układ od prawej do lewej

    if (currentShelfLanguage === 'HEB') {

        shelfContent.classList.add('shelf-rtl');

    } else {

        shelfContent.classList.remove('shelf-rtl');

    }



    shelfContent.innerHTML = rows.map(r => {

        const id = r.c[0] ? r.c[0].v : '';

        const imgUrl = getVal(r.c[23]) || defaultUrl;

        

        // DYNAMICZNE POBIERANIE DANYCH W ZALEŻNOŚCI O WYBRANEGO JĘZYKA

        let title, author, year, place;



        if (currentShelfLanguage === 'HEB') {

            title = getVal(r.c[2]) || "ללא כותרת";       // Kolumna C (indeks 2)

            author = getVal(r.c[4]) || "";               // Kolumna E (indeks 4)

            year = getVal(r.c[6]) || "";                 // Kolumna G (indeks 6)

            place = getVal(r.c[22]) || getVal(r.c[7]) || ""; // Kolumna W (indeks 22), alternatywnie PL jeśli brak

        } else {

            title = getVal(r.c[1]) || "Bez tytułu";      // Kolumna B (indeks 1)

            author = getVal(r.c[3]) || "";               // Kolumna D (indeks 3)

            year = getVal(r.c[5]) || "";                 // Kolumna F (indeks 5)

            place = getVal(r.c[7]) || "";                // Kolumna H (indeks 7)

        }

        

        const isDefault = imgUrl.includes("teatrnn.jpeg");

        const rtlAttr = currentShelfLanguage === 'HEB' ? 'dir="rtl"' : '';



        return `

            <div class="shelf-item" onclick="openModal('${id}')">

                <div class="img-container">

                    <img src="${imgUrl}" class="${isDefault ? 'default-img' : ''}" loading="lazy">

                </div>

                <div class="shelf-info" ${rtlAttr}>

                    <div class="shelf-title ${currentShelfLanguage === 'HEB' ? 'font-heb' : ''}">${title}</div>

                    <div class="shelf-author">${author}</div>

                    <div class="shelf-year">${year}</div>

                    <div class="shelf-place">${place}</div>

                </div>

            </div>`;

    }).join('');

}



// FUNKCJA ZMIENIAJĄCA JĘZYK PÓŁKI (wywoływana kliknięciem przycisku)

function toggleShelfLanguage(lang) {

    currentShelfLanguage = lang;

    

    // Wizualna aktualizacja aktywności przycisków

    document.querySelectorAll('.shelf-lang-btn').forEach(btn => {

        btn.classList.remove('active');

    });

    const activeBtn = document.getElementById(`shelf-btn-${lang.toLowerCase()}`);

    if (activeBtn) activeBtn.classList.add('active');



    // Ponowne wyrenderowanie półki przy użyciu aktualnie widocznych/przefiltrowanych wierszy

    // W Twoim kodzie funkcja filterAndSort() ma dostęp do aktualnego stanu, 

    // najbezpieczniej wywołać ją ponownie, by odświeżyć widok:

    filterAndSort();

}



        function parseDMS(dmsStr) {

            try {

                if (!dmsStr) return null;

                const regex = /(\d+)°(\d+)?′?(\d+)?″?([NSEW])/g;

                const parts = []; let m;

                while ((m = regex.exec(dmsStr)) !== null) {

                    let val = parseFloat(m[1]) + (parseFloat(m[2]||0)/60) + (parseFloat(m[3]||0)/3600);

                    if (m[4] === 'S' || m[4] === 'W') val *= -1;

                    parts.push(val);

                }

                return parts.length === 2 ? parts : null;

            } catch(e) { return null; }

        }



        function renderStats() {

            const data = rawRows; 

            const isMobile = window.innerWidth < 768;



            const years = {};

            data.forEach(r => { let y = extractYear(getVal(r.c[5])); if(y > 0) years[y] = (years[y]||0) + 1; });

            const sortedYears = Object.keys(years).sort();

            if(timelineChart) timelineChart.destroy();

            timelineChart = new Chart(document.getElementById('timelineChart'), {

                type: 'bar',

                data: { labels: sortedYears, datasets: [{ label: 'Książki / Books', data: sortedYears.map(y => years[y]), backgroundColor: '#1a1a1a' }] },

                options: { responsive: true, maintainAspectRatio: false, scales: { y: { display: false }, x: { grid: { display: false } } }, plugins: { legend: { display: false } } }

            });

// --- LOGIKA SANKEY DIAGRAM (v7 - Całkowita unifikacja barw i brak warstw) ---

            const authCountsS = {};

            data.forEach(r => {

                let a = getVal(r.c[3]);

                if (!isUnknown(a)) authCountsS[a] = (authCountsS[a] || 0) + 1;

            });



            const top5SankeyAuth = Object.entries(authCountsS)

                .sort((a, b) => b[1] - a[1])

                .slice(0, 5)

                .map(e => e[0]);



            const sankeyFlows = [];

            const citiesInSankey = new Set();

            data.forEach(r => {

                let auth = getVal(r.c[3]);

                let city = getVal(r.c[7]) || "Nieznane / Unknown";

                if (top5SankeyAuth.includes(auth)) {

                    sankeyFlows.push({ from: auth, to: city, flow: 1 });

                    citiesInSankey.add(city);

                }

            });



            const aggregatedFlows = Object.values(sankeyFlows.reduce((acc, curr) => {

                const key = curr.from + "|" + curr.to;

                if (!acc[key]) acc[key] = { ...curr };

                else acc[key].flow += 1;

                return acc;

            }, {}));



  // 1. Definiujemy kolory z kanałem Alpha (identycznym jak późniejsze alpha linii)

            const sankeyPalette = {

                [top5SankeyAuth[0]]: 'rgba(93, 173, 226, 0.8)', // Przytłumiony niebieski

                [top5SankeyAuth[1]]: 'rgba(235, 152, 78, 0.8)', // Przytłumiony pomarańczowy

                [top5SankeyAuth[2]]: 'rgba(236, 112, 99, 0.8)', // Przytłumiony malinowy

                [top5SankeyAuth[3]]: 'rgba(72, 201, 176, 0.8)', // Przytłumiony turkusowy

                [top5SankeyAuth[4]]: 'rgba(244, 208, 63, 0.8)'  // Przytłumiony żółty

            };



            const greyNode = 'rgba(189, 195, 199, 0.8)'; // Szary dla miast



            if (window.sankeyInstance) window.sankeyInstance.destroy();

            const ctxSankey = document.getElementById('sankeyChart').getContext('2d');



            window.sankeyInstance = new Chart(ctxSankey, {

                type: 'sankey',

                data: {

                    datasets: [{

                        data: aggregatedFlows,

                        // WYMUSZENIE KOLORÓW WĘZŁÓW - używamy RGBA dla spójności

                        colorNodes: (context) => {

                            const name = context.node.id;

                            return sankeyPalette[name] ? sankeyPalette[name] : greyNode;

                        },

                        // KOLORY LINII

                        colorFrom: (c) => sankeyPalette[c.dataset.data[c.dataIndex].from],

                        colorTo: (c) => {

                            const active = c.chart.getActiveElements();

                            if (active.length > 0 && active[0].index === c.dataIndex) {

                                return sankeyPalette[c.dataset.data[c.dataIndex].from];

                            }

                            return greyNode;

                        },

                        colorMode: 'gradient',

                        nodeColorMode: 'fixed',



                        // KLUCZOWE: Ustawiamy alpha na 1, bo przezroczystość mamy w RGBA

                        alpha: 1, 

                        hoverAlpha: 1,



                        borderWidth: 0,

                        nodeWidth: 15,

                        nodePadding: 20

                    }]

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: { display: false },

                        tooltip: {

                            backgroundColor: 'rgba(26, 26, 26, 0.9)',

                            callbacks: {

                                label: (c) => {

                                    const d = c.dataset.data[c.dataIndex];

                                    return ` ${d.from} → ${d.to}: ${d.flow}`;

                                }

                            }

                        }

                    }

                }

            });

// Słupki poziome (Lokalizacje) - Paleta Modern Archive

const locs = {};

            data.forEach(r => { 

                let rawVal = getVal(r.c[11]);

                // Usuwamy zbędne spacje i zamieniamy na małe litery do testu

                let cleanVal = rawVal ? rawVal.trim() : "";

                let testVal = cleanVal.toLowerCase();



                let finalLabel;

                // Jeśli komórka spełnia warunek "nieznana" (pusta, myślnik, lub zawiera frazę unknown/nieznan)

                if (isUnknown(cleanVal) || testVal.includes('unknown') || testVal.includes('nieznan')) {

                    finalLabel = "Nieznana / Unknown";

                } else {

                    finalLabel = cleanVal; // Zachowaj oryginalną pisownię z Excela

                }



                if (finalLabel) {

                    locs[finalLabel] = (locs[finalLabel] || 0) + 1; 

                }

            });



            const locData = Object.entries(locs).sort((a, b) => b[1] - a[1]);

            const labels = locData.map(d => d[0]);

            const values = locData.map(d => d[1]);



            if(locChart) locChart.destroy();



            // Dynamiczne dostosowanie wysokości kontenera na mobile

            if(isMobile) document.getElementById('chart-loc-container').style.height = (labels.length * 40) + "px";



            locChart = new Chart(document.getElementById('locChart'), {

                type: 'bar',

                data: { 

                    labels: labels, 

                    datasets: [{ 

                        data: values, 

                        backgroundColor: ['#2c3e50', '#5a6a7a', '#7f8c8d', '#95a5a6', '#bdc3c7', '#d5dbdb', '#e5e8e8'],

                        borderRadius: 0

                    }] 

                },

options: { 

                indexAxis: 'y',

                responsive: true, 

                maintainAspectRatio: false, 

                layout: {

                    padding: {

                        left: 10 // Subtelny margines od krawędzi

                    }

                },

                interaction: {

                    mode: 'y',

                    intersect: false

                },

                plugins: { 

                    legend: { display: false },

                    tooltip: { 

                        enabled: true,

                        backgroundColor: 'rgba(26, 26, 26, 0.9)',

                        padding: 10,

                        // To wymusi pokazanie PEŁNEJ nazwy w dymku, nawet jeśli na osi jest skrócona

                        callbacks: {

                            title: function(context) {

                                return context[0].label;

                            }

                        }

                    }

                },

                scales: {

                    x: { 

                        beginAtZero: true, 

                        grid: { display: false },

                        ticks: { stepSize: 50 } 

                    },

                    y: { 

                        grid: { display: false },

                        ticks: { 

                            autoSkip: false, 

                            font: { size: isMobile ? 9 : 11, weight: 'bold' }, 

                            color: '#1a1a1a',

                            // FUNKCJA SKRACAJĄCA TEKST - agresywniejsza na mobile

                            callback: function(value) {

                                let label = this.getLabelForValue(value);

                                const maxLength = isMobile ? 18 : 35; 

                                if (label.length > maxLength) {

                                    return label.substring(0, maxLength) + '...';

                                }

                                return label;

                            }

                        }

                    }

                }

            }

            });

// --- LOGIKA: PIECZĘCIE Z PROCENTAMI ---

            const stampsCounts = {};

            let totalStamps = 0; // Suma do obliczenia procentów



            data.forEach(r => {

                if (r.c && r.c[28]) {

                    let val = getVal(r.c[28]); 

                    if (val && val !== "-" && val !== "---") {

                        val.split(',').forEach(s => {

                            let stamp = s.trim();

                            if (stamp) {

                                stampsCounts[stamp] = (stampsCounts[stamp] || 0) + 1;

                                totalStamps++; 

                            }

                        });

                    }

                }

            });



            const sortedStamps = Object.entries(stampsCounts).sort((a, b) => b[1] - a[1]);

            

            // Tworzymy etykiety z dołączonym procentem, np. "Typ 1b (15%)"

            const stampsLabels = sortedStamps.map(d => {

                const percentage = ((d[1] / totalStamps) * 100).toFixed(1);

                return `${d[0]} (${percentage}%)`;

            });

            const stampsValues = sortedStamps.map(d => d[1]);



            if (stampsChart) stampsChart.destroy();



            const ctxStamps = document.getElementById('stampsChart').getContext('2d');

            

            // Dynamiczne dopasowanie wysokości dla wielu typów

            const container = document.getElementById('chart-stamps-container');

            if (sortedStamps.length > 10) {

                container.style.height = (sortedStamps.length * 30) + "px";

            } else {

                container.style.height = "350px";

            }



            stampsChart = new Chart(ctxStamps, {

                type: 'bar',

                data: {

                    labels: stampsLabels,

                    datasets: [{

                        label: 'Liczba wystąpień / Count',

                        data: stampsValues,

                        backgroundColor: '#c73848',

                        borderRadius: 0

                    }]

                },

                options: {

                    indexAxis: 'y',

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: { 

                        legend: { display: false },

                        // Dodatkowe info w dymku po najechaniu

                        tooltip: {

                            callbacks: {

                                label: function(context) {

                                    const val = context.raw;

                                    const pct = ((val / totalStamps) * 100).toFixed(1);

                                    return ` Ilość: ${val} (${pct}%)`;

                                }

                            }

                        }

                    },

                    scales: {

                        x: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { display: false } },

                        y: { 

                            ticks: { 

                                autoSkip: false, 

                                font: { size: 11, weight: 'bold' } 

                            }, 

                            grid: { display: false }

                        }

                    }

                }

            });

// --- ZAAWANSOWANA ANALIZA ZBIORÓW SZAPIRY I STARODRUKÓW ---

// --- ZAAWANSOWANA ANALIZA ZBIORÓW SZAPIRY I STARODRUKÓW ---

let countSzapira = 0;

let countOthers = 0;

let oldPrintsSzapira = 0;   

let modernBooksSzapira = 0; 

let oldPrintsOthers = 0;    

let modernBooksOthers = 0;  



data.forEach(r => {

    let isSzapira = r.c && r.c[29] && getVal(r.c[29]).toLowerCase() === 'x';

    let yearRaw = r.c[5] ? getVal(r.c[5]) : "";

    let year = parseInt(yearRaw);

    let isOld = (!isNaN(year) && year > 0 && year <= 1800);



    if (isSzapira) {

        countSzapira++;

        if (isOld) oldPrintsSzapira++;

        else modernBooksSzapira++;

    } else {

        countOthers++;

        if (isOld) oldPrintsOthers++;

        else modernBooksOthers++;

    }

});



const totalAll = countSzapira + countOthers;

const totalOld = oldPrintsSzapira + oldPrintsOthers;



// AKTUALIZACJA METRYCZEK (DOM)

document.getElementById('stat-szapira-count').innerText = countSzapira;

document.getElementById('stat-szapira-percent').innerText = ((countSzapira / totalAll) * 100).toFixed(1) + "%";

document.getElementById('stat-szapira-old').innerText = oldPrintsSzapira;

document.getElementById('stat-szapira-old-pct').innerText = countSzapira > 0 ? ((oldPrintsSzapira / countSzapira) * 100).toFixed(1) + "%" : "0%";



document.getElementById('stat-others-count').innerText = countOthers;

document.getElementById('stat-others-percent').innerText = ((countOthers / totalAll) * 100).toFixed(1) + "%";

document.getElementById('stat-others-old').innerText = oldPrintsOthers;

document.getElementById('stat-others-old-pct').innerText = countOthers > 0 ? ((oldPrintsOthers / countOthers) * 100).toFixed(1) + "%" : "0%";



document.getElementById('stat-total-count').innerText = totalAll;

document.getElementById('stat-total-old').innerText = totalOld;

document.getElementById('stat-total-old-pct').innerText = totalAll > 0 ? ((totalOld / totalAll) * 100).toFixed(1) + "%" : "0%";



// --- RENDEROWANIE WYKRESU DONUT ---

if (szapiraChart) szapiraChart.destroy();



const ctxSzapira = document.getElementById('szapiraChart').getContext('2d');

szapiraChart = new Chart(ctxSzapira, {

    type: 'doughnut',

    data: {

        datasets: [

            // PIERŚCIEŃ ZEWNĘTRZNY: Zbiory Szapiry vs Pozostałe

            {

                label: 'Kolekcja / Collection',

                data: [countSzapira, countOthers],

                backgroundColor: ['#c73848', '#d1d1d1'], 

                hoverBackgroundColor: ['#a52a3a', '#bcbcbc'], 

                hoverOffset: 0,

                labels: [

                    'Zbiory Szapiry / The Shapira Collection', 

                    'Pozostałe / Other'

                ],

                borderWidth: 2,

                weight: 1

            },

            // PIERŚCIEŃ WEWNĘTRZNY: Podział na wiek

            {

                label: 'Typ druku / Print Type',

                data: [oldPrintsSzapira, modernBooksSzapira, oldPrintsOthers, modernBooksOthers],

                backgroundColor: [

                    '#8b1e2a', 

                    'rgba(199, 56, 72, 0.3)', 

                    '#777777', 

                    '#e8e8e8'

                ],

                hoverBackgroundColor: [

                    '#5c131b',

                    'rgba(199, 56, 72, 0.5)', 

                    '#555555', 

                    '#dcdcdc'

                ],

                hoverOffset: 0,

                labels: [

                    'Starodruki / Old Prints', 

                    'Druki nowsze / Modern Prints', 

                    'Starodruki / Old Prints', 

                    'Druki nowsze / Modern Prints'

                ],

                borderWidth: 2,

                weight: 0.8

            }

        ]

    },

    options: {

        responsive: true,

        maintainAspectRatio: false,

        cutout: '65%', 

        layout: {

            padding: 25 

        },

        plugins: {

            legend: { display: false },

            tooltip: {

                callbacks: {

                    label: function(context) {

                        const val = context.raw;

                        const pct = ((val / totalAll) * 100).toFixed(1);

                        const label = context.dataset.labels[context.dataIndex];

                        return ` ${label}: ${val} (${pct}%)`;

                    }

                }

            }

        }

    }

});

// --- ANALIZA DANYCH TEMATYCZNYCH ---

const subjectCounts = {};

let totalValidEntries = 0;



data.forEach(r => {

    let val = (r.c && r.c[31] && r.c[31].v) ? String(r.c[31].v) : "";

    if (!val || val === "---" || val === "") return;



    val.split(';').forEach(p => {

        let parts = p.split('/');

        let plPart = parts[0] ? parts[0].trim() : "";

        let enPart = parts[1] ? parts[1].trim() : "";



        // Ucinanie kropki i myślnika w obu językach

        let cleanPL = plPart.split('.')[0].split('--')[0].trim();

        let cleanEN = enPart.split('.')[0].split('--')[0].trim();



        if (cleanPL) {

            let finalLabel = cleanEN ? `${cleanPL} / ${cleanEN}` : cleanPL;

            subjectCounts[finalLabel] = (subjectCounts[finalLabel] || 0) + 1;

            totalValidEntries++;

        }

    });

});



const sortedEntries = Object.entries(subjectCounts).sort((a, b) => b[1] - a[1]);

const top10 = sortedEntries.slice(0, 10);

const others = sortedEntries.slice(10);



// OBLICZANIE MAKSYMALNEJ WARTOŚCI DLA SKALOWANIA SŁUPKÓW

const maxPercent = Math.max(...top10.map(x => (x[1] / totalValidEntries) * 100));

const dynamicMax = Math.ceil(maxPercent + (maxPercent * 0.1)); // Dodaje 10% zapasu, żeby słupek nie dotykał ramki



// --- RENDEROWANIE WYKRESU ---

if (window.subjectChart) window.subjectChart.destroy();

const ctxS = document.getElementById('subjectBarChart').getContext('2d');



window.subjectChart = new Chart(ctxS, {

    type: 'bar',

    data: {

        labels: top10.map(x => x[0]),

        datasets: [{

            data: top10.map(x => ((x[1] / totalValidEntries) * 100).toFixed(1)),

            backgroundColor: '#2c3e50',

            borderWidth: 0,

            hoverBackgroundColor: '#212e3b',

            barThickness: 22 // Grubsze słupki, by lepiej wyglądały na dużej szerokości

        }]

    },

    options: {

        indexAxis: 'y',

        responsive: true,

        maintainAspectRatio: false,

        layout: {

            // Zmniejszamy paddingi, by wykres "rozepchał" się wewnątrz chart-card

            padding: { left: 0, right: 40, top: 10, bottom: 0 }

        },

        scales: {

            x: {

                display: true,

                max: dynamicMax, // DZIĘKI TEMU SŁUPKI SĄ DŁUŻSZE

                grid: { color: '#f0f0f0', drawBorder: false },

                ticks: {

                    callback: value => value + "%",

                    font: { size: 10, family: "'Segoe UI'" },

                    color: '#aaa'

                }

            },

            y: {

                grid: { display: false },

                ticks: {

                    color: '#1a1a1a',

                    font: { family: "'Segoe UI'", weight: 'bold', size: 11 },

                    // Zapewnia, że długie nazwy PL/EN nie zostaną ucięte

                    autoSkip: false

                }

            }

        },

        plugins: {

            legend: { display: false },

            tooltip: {

                backgroundColor: 'rgba(26, 26, 26, 0.9)',

                cornerRadius: 4,

                titleFont: { family: "'Segoe UI'" },

                bodyFont: { family: "'Segoe UI'" },

                callbacks: {

                    label: (ctx) => ` ${ctx.parsed.x}% udziału / share`

                }

            }

        }

    }

});



// --- METRYCZKI (BEZ POGRUBIENIA, PROCENTY) ---

const mContainer = document.getElementById('subject-metrics-container');

if (mContainer) {

    mContainer.innerHTML = others.map(([name, count]) => {

        const percent = ((count / totalValidEntries) * 100).toFixed(1);

        return `

            <div style="

                display: flex; 

                justify-content: space-between; 

                align-items: center;

                font-size: 11px; 

                font-family: 'Segoe UI', sans-serif; 

                padding: 4px 0; 

                break-inside: avoid;

                color: #555;

            ">

                <span style="padding-right: 5px; text-align: left;">${name}</span>

                <div style="flex-grow: 1; border-bottom: 1px dotted #eee; margin: 0 8px; height: 10px;"></div>

                <span style="color: #2c3e50; font-weight: normal; white-space: nowrap;">

                    <span style="color: #ccc; margin-right: 5px;">&bull;</span>${percent}%

                </span>

            </div>

        `;

    }).join('');

}

            mapInstance.eachLayer(l => { if(l instanceof L.Marker) mapInstance.removeLayer(l); });

            const cities = {};

            data.forEach(r => {

                let name = getVal(r.c[7]), coords = parseDMS(getVal(r.c[9]));

                if(coords) {

                    let key = coords.join(',');

                    if(!cities[key]) cities[key] = { pos: coords, name: name, count: 0 };

                    cities[key].count++;

                }

            });

            Object.values(cities).forEach(c => {

                L.marker(c.pos).addTo(mapInstance).bindPopup(`<b>${c.name}</b><br>Książek / Books: ${c.count}`);

            });

            renderNetworkGraph(data); // <--- TUTAJ TO POWINNO BYĆ

        }

        let networkInstance = null;

function renderNetworkGraph(data, mode = 'author') {

            const container = document.getElementById('network-graph');

    if (networkInstance !== null) {

        networkInstance.destroy();

        networkInstance = null;

    }



    const isAuthorMode = mode === 'author';

const categoryIndex = isAuthorMode ? 3 : 10; // 3 to autor, 10 to drukarz

const limit = isAuthorMode ? 10 : 5;



const counts = {};

data.forEach(r => {

    let val = getVal(r.c[categoryIndex]);

    if (val && val !== '-' && !val.toLowerCase().includes('brak')) {

        counts[val] = (counts[val] || 0) + 1;

    }

});



const topItems = Object.entries(counts)

    .sort((a, b) => b[1] - a[1])

    .slice(0, limit)

    .map(e => e[0]);



            const nodes = new vis.DataSet();

            const edges = new vis.DataSet();

            const addedNodes = new Set();



            // Centralny punkt

nodes.add({

    id: 'center',

    label: 'Jeszywas Chachmej Lublin',

    title: 'Jeszywas Chachmej Lublin', // Dymek

    shape: 'dot',

    size: 80, // Zwiększony rozmiar

borderWidth: 0, // Całkowite usunięcie ramki

    borderWidthSelected: 0, // Usunięcie ramki również po kliknięciu

    color: {

        background: '#f2c635',

        border: '#f2c635', // Dla pewności ustawiamy kolor ramki identyczny z tłem

        highlight: {

            background: '#f2c635',

            border: '#f2c635'

        }

    },

chosen: {

        node: function(values, id, selected, hovering) {

            if (hovering) {

                values.color = '#f2c635'; // Zmuszamy do zachowania oryginalnego koloru

                values.borderWidth = 0;

            }

        }

    },

    font: { size: 18, weight: 'bold' }

});

addedNodes.add('center');



            data.forEach(r => {

    const currentItem = getVal(r.c[categoryIndex]);

    if (topItems.includes(currentItem)) {

        const title = getVal(r.c[1]);

        const author = getVal(r.c[3]);

        const city = getVal(r.c[7]);

        const printer = getVal(r.c[10]);

        const year = getVal(r.c[5]);

        const bookId = 'book_' + Math.random().toString(36).substr(2, 9);



        // TYTUŁY - Pomarańczowe koła z podpisem

        nodes.add({

            id: bookId,

            label: title.substring(0, 15) + '...', // Podpis pod kołem

            title: 'Tytuł / Title: ' + title, // Dymek

            shape: 'dot',

            size: 20,

            color: '#c5c9c9' // Orange

        });



edges.add({ 

            from: 'center', 

            to: bookId, 

            color: {

                color: '#c5c9c9',      // Kolor linii

                highlight: '#c5c9c9',  // Kolor po kliknięciu

                hover: '#c5c9c9',      // Kolor po najechaniu

                inherit: false         // WYMAGANE: wyłącza dziedziczenie koloru z Jeszywy

            },

    chosen: {

        edge: function(values, id, selected, hovering) {

            if (hovering) {

                values.width = 1; // Zapobiega pogrubieniu linii przy najechaniu

            }

        }

    },

            length: 100

        });



        // AUTORZY - Niebieskie koła z podpisem

        if (author && author !== '-') {

            if (!addedNodes.has(author)) {

                nodes.add({ 

                    id: author, 

                    label: author, // Podpis pod kołem

                    title: 'Autor / Author: ' + author, // Dymek

                    shape: 'dot', 

                    size: (isAuthorMode ? 25 : 15),

                    color: '#678ed6' // Blue

                });

                addedNodes.add(author);

            }

           edges.add({ 

    from: bookId, 

    to: author, 

    color: '#678ed6', 

    length: 250 // Dłuższa linia wypychająca autorów dalej

});

        }



        // DRUKARZ - Turkusowy rąb (diamond) z podpisem

        if (printer && printer !== '-') {

            if (!addedNodes.has(printer)) {

                nodes.add({ 

                    id: printer, 

                    label: printer, // Podpis pod rąbem

                    title: 'Drukarz / Printer: ' + printer, // Dymek

                    shape: 'diamond', 

                    size: (isAuthorMode ? 15 : 30), 

                    color: '#6abbc4' // Turquoise

                });

                addedNodes.add(printer);

            }

            edges.add({ 

                from: bookId, 

                to: printer, 

                color: '#6abbc4',

                title: 'Rok wydania / Year: ' + year // Dymek na linii

            });

        }



        // MIASTA - Najmniejsze czerwone koła

        if (city && city !== '-') {

            if (!addedNodes.has(city)) {

                nodes.add({ 

                    id: city, 

                    label: city, // Podpis pod kołem

                    title: 'Miejsce / Place: ' + city, // Dymek

                    shape: 'dot', 

                    size: 12, // Najmniejsze

                    color: '#c73848' // Red

                });

                addedNodes.add(city);

            }

           edges.add({ 

    from: bookId, 

    to: city, 

    dashes: true, 

    color: '#c73848', 

    length: 350 // Miasta będą w najbardziej zewnętrznym kręgu

});

        }

    }

});



            const graphData = { nodes: nodes, edges: edges };

const options = {

    interaction: { hover: true, tooltipDelay: 200 },

    physics: { 

        stabilization: { iterations: 150 },

        barnesHut: { 

            gravitationalConstant: -5000, // Silniejsze odpychanie punktów

            springConstant: 0.04,         // Elastyczność sprężyn

            springLength: 200             // Domyślna baza długości

        }

    }

};

            networkInstance = new vis.Network(container, graphData, options);

        }

        function updateGraph() {

    const mode = document.getElementById('graph-mode').value;

    if (window.currentData) {

        renderNetworkGraph(window.currentData, mode);

    }

}

// MODUŁ PROWENIENCJI - LOGIKA CELU (DESTINATION-BASED)

const ProvenanceModule = {

    instance: null,



    init: function(text, detailsText, containerId) {

        const container = document.getElementById(containerId);

        if (!containerId) return;

        if (!container || !text || text === "-") {

            if (container) container.innerHTML = "";

            return;

        }



        if (this.instance) { 

            this.instance.destroy(); 

            this.instance = null; 

        }



        const nodes = new vis.DataSet();

        const edges = new vis.DataSet();

        

        // Rozbijamy opisy z kolumny Z

        const detailsArray = detailsText ? detailsText.split('|').map(d => d.trim()) : [];

        const parts = text.split(/([>|])/g).map(p => p.trim()).filter(p => p !== "");

        

        let lastNodeId = null;

        let nodeIndex = 0;

        let nodeCounter = 0; // Licznik pudełek (węzłów)



        parts.forEach((part, index) => {

            if (part === ">" || part === "|") return;



            const actionMatch = part.match(/\(([^)]+)\)$/);

            const currentAction = actionMatch ? actionMatch[1] : ""; 

            const cleanContent = part.replace(/\s*\([^)]+\)$/, "").trim();

            

            let nodeColor = "#2B7CE9";

            if (currentAction.match(/Grabież|Loot/i)) nodeColor = "#c73848";

            if (currentAction.match(/Dar|Donation/i)) nodeColor = "#28a745";



            const nodeId = nodeIndex++;

            

            // 1. Pobieramy opis z tablicy

            let currentTooltip = detailsArray[nodeCounter] || "";



            // 2. Przygotowujemy obiekt węzła BEZ dymka

            const nodeData = {

                id: nodeId,

                label: cleanContent.replace(/:/g, '\n'),

                shape: 'box',

                shapeProperties: { borderRadius: 0 },

                margin: 10,

                color: { background: '#fff', border: nodeColor },

                font: { size: 12, multi: true, align: 'center' },

                borderWidth: 2

            };



            // 3. KLUCZOWY WARUNEK: Jeśli to nie jest "0!" i nie jest puste, dodaj dymek

            if (currentTooltip !== "0!" && currentTooltip.trim() !== "") {

                nodeData.title = currentTooltip;

            }



            // 4. Dodajemy gotowy obiekt do zbioru węzłów

            nodes.add(nodeData);



            // --- Logika połączeń (edges) pozostaje bez zmian ---

            if (lastNodeId !== null) {

                const prevSeparator = parts[index - 1];

                if (prevSeparator === ">") {

                    edges.add({

                        from: lastNodeId,

                        to: nodeId,

                        label: currentAction,

                        arrows: 'to',

                        color: { color: nodeColor, opacity: 0.8 },

                        font: { size: 10, background: '#ffffff', strokeWidth: 0 }

                    });

                } else if (prevSeparator === "|") {

                    edges.add({

                        from: lastNodeId,

                        to: nodeId,

                        arrows: '',

                        dashes: true,

                        color: { color: '#c2c0c0', opacity: 0.4 },

                        label: "" 

                    });

                }

            }

            lastNodeId = nodeId;

            nodeCounter++; // Zwiększamy licznik po dodaniu każdego węzła

        });



        const options = {

            physics: { 

                enabled: true, 

                solver: 'repulsion', 

                repulsion: { nodeDistance: 250, centralGravity: 0.1 } 

            },

            interaction: { 

                dragNodes: true, 

                zoomView: true, 

                dragView: true,

                hover: true, // Wymagane dla dymków

                selectConnectedEdges: false,

                tooltipDelay: 300 // Dymek pojawi się po 0.3s najechania

            },

            nodes: {

                chosen: {

                    node: function(values, id, selected, hovering) {

                        values.borderWidth = 3; // Tylko lekkie pogrubienie ramki przy kliknięciu

                    }

                }

            },

            edges: {

                hoverWidth: 0,     // Linia nie grubnie przy najechaniu

                selectionWidth: 0, // Linia nie grubnie przy kliknięciu

                chosen: {

                    edge: function(values, id, selected, hovering) {},

                    label: function(values, id, selected, hovering) {}

                }

            }

        };



        this.instance = new vis.Network(container, { nodes, edges }, options);

    }

};

    // Globalna zmienna zainicjowana raz

let currentSlide = 0;



function moveSlide(direction, btnElement) {

    // Szukamy kontenera o nowej nazwie

    const container = btnElement.closest('.photo-slider-container');

    const wrapper = container.querySelector('.photo-slider-wrapper');

    const slides = wrapper.querySelectorAll('img');

    const totalSlides = slides.length;



    if (totalSlides <= 1) return;



    let currentIdx = parseInt(container.getAttribute('data-current-slide') || "0");

    currentIdx = (currentIdx + direction + totalSlides) % totalSlides;

    

    container.setAttribute('data-current-slide', currentIdx);

    wrapper.style.transform = `translateX(-${currentIdx * 100}%)`;

}

        // Funkcja tworząca Lightbox przy pierwszym kliknięciu

function openLightbox(src, fromGallery) {

    let overlay = document.getElementById('lightbox-overlay');

    if (!overlay) {

        overlay = document.createElement('div');

        overlay.id = 'lightbox-overlay';

        overlay.innerHTML = `

            <span class="lightbox-close">&times;</span>

            <button class="lightbox-btn lightbox-prev" id="lb-prev">&#10094;</button>

            <button class="lightbox-btn lightbox-next" id="lb-next">&#10095;</button>

            <img id="lightbox-img" src="">

        `;

        document.body.appendChild(overlay);

        

        overlay.onclick = function(e) {

            if (e.target.id === 'lightbox-overlay' || e.target.className === 'lightbox-close') {

                overlay.style.display = 'none';

            }

        };



        document.getElementById('lb-next').onclick = function(e) {

            e.stopPropagation();

            const nextBtn = document.querySelector('.photo-next-btn');

            if (nextBtn) { nextBtn.click(); syncLightbox(); }

        };



        document.getElementById('lb-prev').onclick = function(e) {

            e.stopPropagation();

            const prevBtn = document.querySelector('.photo-prev-btn');

            if (prevBtn) { prevBtn.click(); syncLightbox(); }

        };

    }



    const imgElement = document.getElementById('lightbox-img');

    imgElement.src = src;

    overlay.style.display = 'flex';



    if (fromGallery) {

        // Jeśli kliknięto w galerię, ustawiamy slider pod spodem na tym zdjęciu

        const container = document.querySelector('.photo-slider-container');

        if (container) {

            const slides = Array.from(container.querySelectorAll('.photo-slider-wrapper img'));

            const clickedIdx = slides.findIndex(img => img.src === src);

            if (clickedIdx !== -1) {

                container.setAttribute('data-current-slide', clickedIdx);

                const wrapper = container.querySelector('.photo-slider-wrapper');

                if (wrapper) wrapper.style.transform = `translateX(-${clickedIdx * 100}%)`;

            }

        }

        imgElement.setAttribute('data-mode', 'gallery');

        syncLightbox(); 

    } else {

        // Jeśli kliknięto w miniaturę główną, blokujemy nawigację

        imgElement.setAttribute('data-mode', 'main');

        document.getElementById('lb-prev').style.display = 'none';

        document.getElementById('lb-next').style.display = 'none';

    }

}



// Pomocnicza funkcja synchronizująca obraz i widoczność strzałek

function syncLightbox() {

    const lbImg = document.getElementById('lightbox-img');

    if (!lbImg || lbImg.getAttribute('data-mode') === 'main') return; // STOP



    const container = document.querySelector('.photo-slider-container');

    const lbPrev = document.getElementById('lb-prev');

    const lbNext = document.getElementById('lb-next');



    if (container && lbImg) {

        const slides = container.querySelectorAll('.photo-slider-wrapper img');

        const currentIdx = parseInt(container.getAttribute('data-current-slide') || "0");

        

        if (slides[currentIdx]) lbImg.src = slides[currentIdx].src;



        const showBtns = slides.length > 1 ? 'block' : 'none';

        if (lbPrev) lbPrev.style.display = showBtns;

        if (lbNext) lbNext.style.display = showBtns;

    }

}

// Obsługa klawiatury dla całego dokumentu

document.addEventListener('keydown', function(e) {

    const lightbox = document.getElementById('lightbox-overlay');

    const modal = document.getElementById('modalOverlay');

    const isLightboxOpen = lightbox && lightbox.style.display === 'flex';

    const isModalOpen = modal && modal.style.display === 'flex';



    // 1. Obsługa klawisza ESC

if (e.key === "Escape") {

        if (isLightboxOpen) {

            lightbox.style.display = 'none';

        } else if (isModalOpen) {

            closeModal();

        }

    }



    // 2. Obsługa strzałek (tylko gdy cokolwiek jest otwarte)

    if (isModalOpen) {

        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {

            const direction = e.key === "ArrowRight" ? 1 : -1;

            const nextBtn = document.querySelector('.photo-next-btn');

            const prevBtn = document.querySelector('.photo-prev-btn');



            // "Klikamy" w przycisk pod spodem, żeby przesunąć slider

            if (direction === 1 && nextBtn) nextBtn.click();

            if (direction === -1 && prevBtn) prevBtn.click();



            // SZLIF: Jeśli lightbox jest otwarty, musimy mu podmienić zdjęcie na to nowe

            if (isLightboxOpen) {

                const container = document.querySelector('.photo-slider-container');

                if (container) {

                    const currentIdx = parseInt(container.getAttribute('data-current-slide') || "0");

                    const slides = container.querySelectorAll('.photo-slider-wrapper img');

                    if (slides[currentIdx]) {

                        document.getElementById('lightbox-img').src = slides[currentIdx].src;

                    }

                }

            }

        }

    }

});

        init();

    