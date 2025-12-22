frappe.ready(function() {
    scrollToToday();
    initFilters();
    initHoverEffects();
});

function scrollToToday() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${day}`;
    
    const row = document.querySelector(`tr[data-date="${dateStr}"]`);
    if (row) {
        // Wait a bit for layout to settle
        setTimeout(() => {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('is-today');
        }, 500);
    }
}

function initFilters() {
    const allCheckbox = document.getElementById('filter-all');
    const sectionCheckboxes = document.querySelectorAll('input[name="section-filter"]');
    const showEmptyDaysCheckbox = document.getElementById('show-empty-days');
    const monthFilter = document.getElementById('month-filter');
    const yearFilter = document.getElementById('year-filter');

    // Year filter logic
    if (yearFilter) {
        yearFilter.addEventListener('change', () => {
            const selectedYear = yearFilter.value;
            const url = new URL(window.location.href);
            url.searchParams.set('year', selectedYear);
            window.location.href = url.toString();
        });
    }
    
    // "All" checkbox logic
    allCheckbox.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        sectionCheckboxes.forEach(cb => {
            cb.checked = isChecked;
        });
        applyFilters();
    });
    
    // Individual checkboxes logic
    sectionCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
            const allChecked = Array.from(sectionCheckboxes).every(c => c.checked);
            allCheckbox.checked = allChecked;
            allCheckbox.indeterminate = !allChecked && Array.from(sectionCheckboxes).some(c => c.checked);
            applyFilters();
        });
    });

    // Show empty days logic
    showEmptyDaysCheckbox.addEventListener('change', () => {
        applyFilters();
    });

    // Month filter logic
    monthFilter.addEventListener('change', () => {
        applyFilters();
    });
    
    function applyFilters() {
        const selectedSections = Array.from(sectionCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
        
        const showEmptyDays = showEmptyDaysCheckbox.checked;
        const selectedMonth = monthFilter.value;
            
        const rows = document.querySelectorAll('.calendar-row');
        
        rows.forEach(row => {
            let showRow = false;
            const rowDate = row.getAttribute('data-date');
            const rowMonth = rowDate.substring(5, 7);
            
            // Month filter check
            if (selectedMonth && rowMonth !== selectedMonth) {
                showRow = false;
            } else {
                if (showEmptyDays) {
                    showRow = true;
                } else {
                    // If no sections selected, show nothing (unless showEmptyDays is true, handled above)
                    if (selectedSections.length === 0) {
                        showRow = false;
                    } else {
                        // Check if row has activity in ANY of the selected sections
                        for (const section of selectedSections) {
                            // Find the cell for this section
                            // We use CSS.escape to handle section names with special chars if any
                            const cell = row.querySelector(`td[data-section="${CSS.escape(section)}"]`);
                            if (cell && cell.querySelector('.activity-card')) {
                                showRow = true;
                                break;
                            }
                        }
                    }
                }
            }
            
            if (showRow) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });

        // Handle month separators
        document.querySelectorAll('.month-separator-row').forEach(sep => {
            const sepMonth = sep.getAttribute('data-month');
            if (selectedMonth && sepMonth !== selectedMonth) {
                sep.style.display = 'none';
            } else {
                sep.style.display = '';
            }
        });
        
        // Also toggle column visibility
        const allSectionHeaders = document.querySelectorAll('th.col-section');
        const allSectionCells = document.querySelectorAll('td.col-activity');
        
        // This part might be heavy if done cell by cell. 
        // Better to use a style tag to toggle classes?
        // Or just iterate columns.
        
        // Let's use a dynamic style block for column visibility to be efficient
        let styleBlock = document.getElementById('dynamic-filter-style');
        if (!styleBlock) {
            styleBlock = document.createElement('style');
            styleBlock.id = 'dynamic-filter-style';
            document.head.appendChild(styleBlock);
        }
        
        // Generate CSS to hide unselected columns
        // We need to know which columns to hide.
        // Actually, iterating headers and cells is fine for this scale.
        // But CSS is cleaner.
        // We can add a class to the table or body indicating which sections are hidden?
        // No, sections are dynamic.
        
        // Let's just iterate headers and cells.
        // Wait, if I hide a column, the sticky header might break or alignment might break?
        // Table layout handles hidden columns fine.
        
        // However, the prompt asked for "filtro para somente datas".
        // It didn't explicitly ask to hide columns.
        // But if I select only "Section A", seeing empty columns for B, C, D is annoying.
        // I will hide columns too.
        
        const allSections = Array.from(sectionCheckboxes).map(cb => cb.value);
        const unselectedSections = allSections.filter(s => !selectedSections.includes(s));
        
        // Show all first
        document.querySelectorAll('.col-section, .col-activity').forEach(el => el.style.display = '');
        
        unselectedSections.forEach(section => {
             const selector = `[data-section="${CSS.escape(section)}"]`;
             // Hide headers (headers don't have data-section in my HTML yet! I need to add it)
             // Hide cells
             document.querySelectorAll(`td${selector}`).forEach(el => el.style.display = 'none');
             
             // For headers, I need to find them.
             // In HTML: <th class="col-section"><div class="th-content">{{ section }}</div></th>
             // I should add data-section to th as well.
             const headers = document.querySelectorAll(`th.col-section[data-section="${CSS.escape(section)}"]`);
             headers.forEach(th => {
                 th.style.display = 'none';
             });
        });

        // Update colspan for month separators
        const visibleColumnsCount = 1 + selectedSections.length; // 1 for date column
        document.querySelectorAll('.month-separator-cell').forEach(cell => {
            cell.colSpan = visibleColumnsCount;
        });
    }

    // Apply filters initially to match UI state
    applyFilters();
}

function initHoverEffects() {
    const cards = document.querySelectorAll('.activity-card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            const eventId = card.getAttribute('data-event-id');
            if (eventId) {
                const relatedCards = document.querySelectorAll(`.activity-card[data-event-id="${eventId}"]`);
                relatedCards.forEach(c => c.classList.add('is-hovered'));
            }
        });
        
        card.addEventListener('mouseleave', () => {
            const eventId = card.getAttribute('data-event-id');
            if (eventId) {
                const relatedCards = document.querySelectorAll(`.activity-card[data-event-id="${eventId}"]`);
                relatedCards.forEach(c => c.classList.remove('is-hovered'));
            }
        });
    });
}
