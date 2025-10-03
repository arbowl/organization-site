/**
 * Committee Compliance Dashboard JavaScript
 * Handles filtering, sorting, charts, and export functionality
 */

class CommitteeDashboard {
    constructor() {
        this.currentData = COMMITTEE_DATA;
        this.filteredData = [...this.currentData];
        this.currentSort = { field: null, direction: 'asc' };
        this.currentPage = 1;
        this.itemsPerPage = 50;
        this.charts = {};
        
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.renderTable();
        this.renderCharts();
        this.updateSummaryStats();
        this.loadFiltersFromURL();
    }

    setupEventListeners() {
        // Committee selector
        document.getElementById('committee-select').addEventListener('change', (e) => {
            window.location.href = `/projects/committees?committee=${e.target.value}`;
        });

        // Filters
        document.getElementById('status-filter').addEventListener('change', () => {
            this.applyFilters();
        });

        // Table sorting
        document.querySelectorAll('[data-sort]').forEach(header => {
            header.addEventListener('click', (e) => {
                const field = e.target.getAttribute('data-sort');
                this.sortTable(field);
            });
        });

        // Export CSV
        document.getElementById('export-csv').addEventListener('click', () => {
            this.exportCSV();
        });

        // Share link
        document.getElementById('share-link').addEventListener('click', () => {
            this.shareLink();
        });
    }

    applyFilters() {
        const statusFilter = document.getElementById('status-filter').value;

        this.filteredData = this.currentData.filter(bill => {
            // Status filter
            if (statusFilter !== 'all' && bill.state !== statusFilter) {
                return false;
            }

            return true;
        });

        this.currentPage = 1;
        this.renderTable();
        this.updateSummaryStats();
        this.updateURL();
    }

    sortTable(field) {
        if (this.currentSort.field === field) {
            this.currentSort.direction = this.currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.currentSort.field = field;
            this.currentSort.direction = 'asc';
        }

        this.filteredData.sort((a, b) => {
            let aVal = a[field];
            let bVal = b[field];

            // Handle null values
            if (aVal === null) aVal = '';
            if (bVal === null) bVal = '';

            // Convert to comparable types
            if (field === 'notice_gap_days') {
                aVal = parseInt(aVal) || 0;
                bVal = parseInt(bVal) || 0;
            } else if (field === 'hearing_date') {
                aVal = new Date(aVal);
                bVal = new Date(bVal);
            }

            if (aVal < bVal) return this.currentSort.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return this.currentSort.direction === 'asc' ? 1 : -1;
            return 0;
        });

        this.renderTable();
        this.updateSortIndicators();
    }

    renderTable() {
        const tbody = document.getElementById('bills-table-body');
        const startIndex = (this.currentPage - 1) * this.itemsPerPage;
        const endIndex = startIndex + this.itemsPerPage;
        const pageData = this.filteredData.slice(startIndex, endIndex);

        tbody.innerHTML = pageData.map(bill => {
            const statusClass = this.getStatusClass(bill.state);
            const noticeGapClass = this.getNoticeGapClass(bill.notice_gap_days);
            
            // Check if effective deadline is different from 60-day deadline (indicates extension)
            const hasExtension = bill.effective_deadline && bill.deadline_60 && 
                                bill.effective_deadline !== bill.deadline_60;
            
            return `
                <tr class="hover:bg-gray-50 cursor-pointer ${statusClass}" 
                    onclick="this.classList.toggle('expanded')" 
                    data-bill-id="${bill.bill_id}">
                    <td class="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        <a href="${bill.bill_url}" target="_blank" class="text-blue-600 hover:text-blue-800">
                            ${bill.bill_id}
                        </a>
                    </td>
                    <td class="px-4 py-4 text-sm text-gray-900 max-w-xs truncate">
                        ${bill.bill_title}
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${bill.hearing_date || 'N/A'}
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${bill.deadline_60 || 'N/A'}
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${hasExtension ? 
                            `<a href="${bill.extension_order_url || '#'}" target="_blank" class="text-blue-600 hover:text-blue-800">${bill.effective_deadline}</a>` :
                            (bill.effective_deadline || 'N/A')
                        }
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm ${noticeGapClass}">
                        ${bill.notice_gap_days !== null ? 
                            `<span class="${bill.notice_gap_days < 10 ? 'bad' : 'ok'}">${bill.notice_gap_days} days</span>` : 
                            'N/A'
                        }
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${bill.reported_out ? 
                            '<span class="ok font-semibold">Yes</span>' : 
                            '<span class="bad font-semibold">No</span>'
                        }
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${bill.summary_present && bill.summary_url ? 
                            `<a href="${bill.summary_url}" target="_blank" class="text-blue-600 hover:text-blue-800">Yes</a>` :
                            (bill.summary_present ? 'Yes' : '—')
                        }
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${bill.votes_present && bill.votes_url ? 
                            `<a href="${bill.votes_url}" target="_blank" class="text-blue-600 hover:text-blue-800">Yes</a>` :
                            (bill.votes_present ? 'Yes' : '—')
                        }
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap">
                        <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${this.getStatusBadgeClass(bill.state)}">
                            ${bill.state}
                        </span>
                    </td>
                </tr>
                <tr class="hidden expanded-row bg-gray-50">
                    <td colspan="10" class="px-4 py-4 text-sm text-gray-700">
                        <div class="space-y-2">
                            <p><strong>Reason:</strong> ${bill.reason || 'N/A'}</p>
                            ${bill.extension_date ? 
                                `<p><strong>Extension Date:</strong> ${bill.extension_date}</p>` : 
                                ''
                            }
                            <div class="grid grid-cols-2 gap-4 text-xs">
                                <div>
                                    <strong>Announcement Date:</strong> ${bill.announcement_date || 'N/A'}
                                </div>
                                <div>
                                    <strong>Notice Status:</strong> ${bill.notice_status || 'N/A'}
                                </div>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        this.renderPagination();
    }

    renderPagination() {
        const totalPages = Math.ceil(this.filteredData.length / this.itemsPerPage);
        const pagination = document.getElementById('table-pagination');
        
        if (totalPages <= 1) {
            pagination.innerHTML = `<p class="text-sm text-gray-700">Showing ${this.filteredData.length} bills</p>`;
            return;
        }

        const startItem = (this.currentPage - 1) * this.itemsPerPage + 1;
        const endItem = Math.min(this.currentPage * this.itemsPerPage, this.filteredData.length);

        pagination.innerHTML = `
            <div class="flex items-center justify-between">
                <p class="text-sm text-gray-700">
                    Showing ${startItem} to ${endItem} of ${this.filteredData.length} bills
                </p>
                <div class="flex space-x-2">
                    <button onclick="dashboard.changePage(${this.currentPage - 1})" 
                            ${this.currentPage === 1 ? 'disabled' : ''}
                            class="px-3 py-1 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
                        Previous
                    </button>
                    <span class="px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded-md">
                        ${this.currentPage} of ${totalPages}
                    </span>
                    <button onclick="dashboard.changePage(${this.currentPage + 1})" 
                            ${this.currentPage === totalPages ? 'disabled' : ''}
                            class="px-3 py-1 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
                        Next
                    </button>
                </div>
            </div>
        `;
    }

    changePage(page) {
        const totalPages = Math.ceil(this.filteredData.length / this.itemsPerPage);
        if (page >= 1 && page <= totalPages) {
            this.currentPage = page;
            this.renderTable();
        }
    }

    renderCharts() {
        this.renderComplianceChart();
        this.updateAccessibilityTables();
    }



    renderComplianceChart() {
        const ctx = document.getElementById('compliance-chart').getContext('2d');
        
        const statusCounts = {
            'compliant': 0,
            'non-compliant': 0,
            'incomplete': 0,
            'unknown': 0
        };

        this.filteredData.forEach(bill => {
            if (statusCounts.hasOwnProperty(bill.state)) {
                statusCounts[bill.state]++;
            }
        });

        if (this.charts.compliance) {
            this.charts.compliance.destroy();
        }

        this.charts.compliance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Compliant', 'Non-Compliant', 'Incomplete', 'Unknown'],
                datasets: [{
                    data: [
                        statusCounts.compliant,
                        statusCounts['non-compliant'],
                        statusCounts.incomplete,
                        statusCounts.unknown
                    ],
                    backgroundColor: [
                        '#22c55e', // green
                        '#ef4444', // red
                        '#f59e0b', // yellow
                        '#6b7280'  // gray
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                aspectRatio: 2,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    updateSummaryStats() {
        const total = this.filteredData.length;
        const compliant = this.filteredData.filter(b => b.state === 'compliant').length;
        const nonCompliant = this.filteredData.filter(b => b.state === 'non-compliant').length;
        const rate = total > 0 ? Math.round((compliant / total) * 100) : 0;

        document.getElementById('total-bills').textContent = total;
        document.getElementById('compliant-bills').textContent = compliant;
        document.getElementById('non-compliant-bills').textContent = nonCompliant;
        document.getElementById('compliance-rate').textContent = rate + '%';
    }

    updateSortIndicators() {
        // Reset all sort indicators
        document.querySelectorAll('[data-sort]').forEach(header => {
            header.setAttribute('aria-sort', 'none');
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) indicator.textContent = '↕️';
        });

        if (this.currentSort.field) {
            const header = document.querySelector(`[data-sort="${this.currentSort.field}"]`);
            if (header) {
                const sortDirection = this.currentSort.direction === 'asc' ? 'ascending' : 'descending';
                header.setAttribute('aria-sort', sortDirection);
                
                const indicator = header.querySelector('.sort-indicator');
                if (indicator) {
                    indicator.textContent = this.currentSort.direction === 'asc' ? '↑' : '↓';
                }
            }
        }
    }

    getStatusClass(state) {
        switch (state) {
            case 'compliant': return 'bg-green-50';
            case 'non-compliant': return 'bg-red-50';
            case 'incomplete': return 'bg-yellow-50';
            default: return 'bg-gray-50';
        }
    }

    getStatusBadgeClass(state) {
        switch (state) {
            case 'compliant': return 'bg-green-100 text-green-800';
            case 'non-compliant': return 'bg-red-100 text-red-800';
            case 'incomplete': return 'bg-yellow-100 text-yellow-800';
            default: return 'bg-gray-100 text-gray-800';
        }
    }

    getNoticeGapClass(days) {
        if (days === null) return 'text-gray-500';
        if (days < 10) return 'text-red-600 font-semibold';
        return 'text-green-600';
    }

    exportCSV() {
        const params = new URLSearchParams();
        params.append('state', document.getElementById('status-filter').value);
        
        window.open(`/projects/committees/export/${SELECTED_CODE}?${params.toString()}`);
    }

    shareLink() {
        const url = new URL(window.location);
        url.searchParams.set('committee', SELECTED_CODE);
        url.searchParams.set('state', document.getElementById('status-filter').value);
        
        navigator.clipboard.writeText(url.toString()).then(() => {
            // Show temporary success message
            const button = document.getElementById('share-link');
            const originalText = button.textContent;
            button.textContent = '✅ Copied!';
            button.classList.add('bg-green-600');
            setTimeout(() => {
                button.textContent = originalText;
                button.classList.remove('bg-green-600');
            }, 2000);
        });
    }

    updateURL() {
        const url = new URL(window.location);
        url.searchParams.set('state', document.getElementById('status-filter').value);
        window.history.replaceState({}, '', url);
    }

    loadFiltersFromURL() {
        const params = new URLSearchParams(window.location.search);
        
        if (params.has('state')) {
            document.getElementById('status-filter').value = params.get('state');
        }
        
        this.applyFilters();
    }

    updateAccessibilityTables() {
        // Update compliance data table for screen readers
        const complianceTableBody = document.getElementById('compliance-table-body');
        if (complianceTableBody) {
            const statusCounts = {
                'Compliant': 0,
                'Non-Compliant': 0,
                'Incomplete': 0,
                'Unknown': 0
            };

            this.filteredData.forEach(bill => {
                switch (bill.state) {
                    case 'compliant': statusCounts['Compliant']++; break;
                    case 'non-compliant': statusCounts['Non-Compliant']++; break;
                    case 'incomplete': statusCounts['Incomplete']++; break;
                    default: statusCounts['Unknown']++; break;
                }
            });

            const total = this.filteredData.length;
            complianceTableBody.innerHTML = Object.entries(statusCounts).map(([status, count]) => {
                const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
                return `<tr><td>${status}</td><td>${count}</td><td>${percentage}%</td></tr>`;
            }).join('');
        }
    }
}

// Initialize dashboard when page loads
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new CommitteeDashboard();
});

// Handle row expansion
document.addEventListener('click', (e) => {
    if (e.target.closest('tr[data-bill-id]')) {
        const row = e.target.closest('tr[data-bill-id]');
        const nextRow = row.nextElementSibling;
        if (nextRow && nextRow.classList.contains('expanded-row')) {
            nextRow.classList.toggle('hidden');
        }
    }
});
