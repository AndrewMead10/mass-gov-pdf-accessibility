function dashboardHandler() {
    return {
        documents: [],
        loading: false,
        loadingPages: {},
        pageGenerateLoading: {},

        async init() {
            await this.loadDocuments();
            // Auto-refresh every 30 seconds for pending/processing documents
            setInterval(() => {
                const hasPendingOrProcessing = this.documents.some(doc =>
                    doc.status === 'pending' || doc.status === 'processing'
                );
                if (hasPendingOrProcessing) {
                    this.loadDocuments();
                }
            }, 30000);
        },

        async loadDocuments() {
            this.loading = true;
            try {
                const response = await fetch('/api/documents');
                if (!response.ok) {
                    throw new Error('Failed to load documents');
                }
                const documents = await response.json();

                // Add expanded property for UI state and normalize reports if needed
                this.documents = documents.map(doc => ({
                    ...doc,
                    accessibility_report_json: this.normalizeReport(doc.accessibility_report_json),
                    expanded: false,
                    page_results: null,
                    sharedPageIssues: [],
                    pageSpecificIssueGroups: [],
                    pageIssueLoading: false,
                    pageIssueError: null,
                    pageIssueIncomplete: false
                }));
            } catch (error) {
                console.error('Failed to load documents:', error);
                showNotification('Failed to load documents', 'error');
            } finally {
                this.loading = false;
            }
        },

        async loadPageResults(document) {
            if (!document || document.page_results !== null || this.loadingPages[document.id]) return;
            this.loadingPages[document.id] = true;
            document.pageIssueLoading = true;
            document.pageIssueError = null;
            document.pageIssueIncomplete = false;
            try {
                const resp = await fetch(`/api/documents/${document.id}/pages/detailed`);
                if (!resp.ok) throw new Error('Failed to load page results');
                const pages = await resp.json();
                document.page_results = pages.map(p => ({
                    ...p,
                    accessibility_report_json: this.normalizeReport(p.accessibility_report_json),
                    _issues: this.getIssuesFromReport(this.normalizeReport(p.accessibility_report_json))
                }));

                this.computePageIssueGroups(document);
                document.pageIssueIncomplete = false; // No longer needed since we get all data at once
            } catch (e) {
                console.error('Failed to load page results:', e);
                showNotification('Failed to load page results', 'error');
                document.pageIssueError = e.message || 'Failed to load page details';
                document.sharedPageIssues = [];
                document.pageSpecificIssueGroups = [];
            } finally {
                document.pageIssueLoading = false;
                this.loadingPages[document.id] = false;
            }
        },

        async refreshDocuments() {
            await this.loadDocuments();
            showNotification('Documents refreshed', 'success');
        },

        async processDocument(documentId) {
            try {
                const response = await fetch(`/api/process/${documentId}`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to start processing');
                }

                showNotification('Processing started', 'success');
                await this.loadDocuments();
            } catch (error) {
                console.error('Failed to start processing:', error);
                showNotification(error.message || 'Failed to start processing', 'error');
            }
        },

        async downloadPDF(documentId) {
            try {
                const response = await fetch(`/api/download/${documentId}`);
                if (!response.ok) {
                    throw new Error('Failed to download PDF');
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `tagged_document_${documentId}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);

                showNotification('Download started', 'success');
            } catch (error) {
                console.error('Download failed:', error);
                showNotification('Download failed', 'error');
            }
        },

        async deleteDocument(documentId) {
            if (!confirm('Are you sure you want to delete this document?')) {
                return;
            }

            try {
                const response = await fetch(`/api/documents/${documentId}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to delete document');
                }

                showNotification('Document deleted successfully', 'success');
                await this.loadDocuments();
            } catch (error) {
                console.error('Failed to delete document:', error);
                showNotification(error.message || 'Failed to delete document', 'error');
            }
        },

        async toggleDocumentExpand(document) {
            document.expanded = !document.expanded;
            if (document.expanded) {
                await this.loadPageResults(document);
            }
        },


        getIssuesFromReport(report) {
            const normalizedReport = this.normalizeReport(report);
            if (!normalizedReport || !normalizedReport['Detailed Report']) return [];
            const sections = normalizedReport['Detailed Report'];
            const issues = [];
            Object.entries(sections).forEach(([sectionName, rules]) => {
                if (Array.isArray(rules)) {
                    rules.forEach(rule => {
                        if (rule && rule.Status && rule.Status !== 'Passed') {
                            issues.push({
                                section: sectionName,
                                rule: rule.Rule || '',
                                description: rule.Description || '',
                                status: rule.Status
                            });
                        }
                    });
                }
            });
            return issues;
        },

        getPageIssues(page) {
            return Array.isArray(page._issues) ? page._issues : [];
        },

        getDocumentIssues(document) {
            return this.getIssuesFromReport(document.accessibility_report_json);
        },

        computePageIssueGroups(document) {
            if (!document.page_results || document.page_results.length === 0) {
                document.sharedPageIssues = [];
                document.pageSpecificIssueGroups = [];
                return;
            }

            const issueMap = new Map();
            const totalPages = document.page_results.length;

            document.page_results.forEach(page => {
                const issues = this.getPageIssues(page);
                const seen = new Set();
                issues.forEach(issue => {
                    const key = this.buildIssueKey(issue);
                    if (seen.has(key)) return;
                    seen.add(key);
                    if (!issueMap.has(key)) {
                        issueMap.set(key, { issue, pages: new Set() });
                    }
                    issueMap.get(key).pages.add(page.page_number);
                });
            });

            const sharedKeys = new Set();
            const sharedIssues = [];
            issueMap.forEach(({ issue, pages }, key) => {
                if (pages.size === totalPages) {
                    sharedKeys.add(key);
                    sharedIssues.push(issue);
                }
            });

            const pageSpecificIssueGroups = document.page_results.map(page => {
                const allIssues = this.getPageIssues(page);
                const issues = allIssues.filter(issue => !sharedKeys.has(this.buildIssueKey(issue)));
                return {
                    page_number: page.page_number,
                    issues,
                    allIssues
                };
            }).filter(group => group.issues.length > 0); // Only include pages with specific issues

            document.sharedPageIssues = sharedIssues;
            document.pageSpecificIssueGroups = pageSpecificIssueGroups;
        },

        buildIssueKey(issue) {
            if (!issue) return '';
            return [issue.section || '', issue.rule || '', issue.description || '', issue.status || ''].join('||');
        },

        normalizeReport(report) {
            if (!report) return null;
            if (typeof report === 'string') {
                try {
                    return JSON.parse(report);
                } catch (error) {
                    console.warn('Failed to parse accessibility report JSON', error);
                    return null;
                }
            }
            return report;
        },

        async generatePageSummaries(document) {
            if (this.pageGenerateLoading[document.id]) return;
            this.pageGenerateLoading[document.id] = true;
            try {
                const resp = await fetch(`/api/process/${document.id}/pages`, { method: 'POST' });
                if (!resp.ok) throw new Error('Failed to start per-page processing');
                showNotification('Started generating per-page summaries', 'success');
                // Poll for results
                const maxAttempts = 20;
                let attempts = 0;
                const poll = async () => {
                    attempts++;
                    // Reset current cache so loadPageResults will refetch
                    document.page_results = null;
                    document.sharedPageIssues = [];
                    document.pageSpecificIssueGroups = [];
                    document.pageIssueError = null;
                    document.pageIssueIncomplete = false;
                    await this.loadPageResults(document);
                    if (document.page_results && document.page_results.length > 0) return;
                    if (attempts < maxAttempts) setTimeout(poll, 3000);
                    else showNotification('Per-page summaries are still processing…', 'info');
                };
                setTimeout(poll, 3000);
            } catch (e) {
                console.error(e);
                showNotification('Failed to generate per-page summaries', 'error');
            } finally {
                this.pageGenerateLoading[document.id] = false;
            }
        },

        formatDate(dateString) {
            return formatDate(dateString);
        },

        getStatusColor(status) {
            switch (status) {
                case 'pending':
                    return 'bg-gray-100 text-gray-800';
                case 'processing':
                    return 'bg-blue-100 text-blue-800';
                case 'completed':
                    return 'bg-green-100 text-green-800';
                case 'failed':
                    return 'bg-red-100 text-red-800';
                default:
                    return 'bg-gray-100 text-gray-800';
            }
        },

        getStatusText(status) {
            switch (status) {
                case 'pending':
                    return 'Pending';
                case 'processing':
                    return 'Processing';
                case 'completed':
                    return 'Completed';
                case 'failed':
                    return 'Failed';
                default:
                    return status;
            }
        },

        getReportSections(document) {
            const report = this.normalizeReport(document.accessibility_report_json);
            if (!report || !report['Detailed Report']) {
                return {};
            }
            return report['Detailed Report'];
        },

        getRuleStatusColor(status) {
            switch (status) {
                case 'Failed':
                    return 'bg-red-50 border-l-4 border-red-400';
                case 'Needs manual check':
                    return 'bg-yellow-50 border-l-4 border-yellow-400';
                case 'Passed':
                    return 'bg-green-50 border-l-4 border-green-400';
                default:
                    return 'bg-gray-50 border-l-4 border-gray-400';
            }
        },

        getRuleStatusBadge(status) {
            switch (status) {
                case 'Failed':
                    return 'bg-red-100 text-red-800';
                case 'Needs manual check':
                    return 'bg-yellow-100 text-yellow-800';
                case 'Passed':
                    return 'bg-green-100 text-green-800';
                default:
                    return 'bg-gray-100 text-gray-800';
            }
        },

        getCountBadgeClass(type) {
            switch (type) {
                case 'failed':
                    return 'bg-red-100 text-red-800';
                case 'manual':
                    return 'bg-yellow-100 text-yellow-800';
                case 'passed':
                    return 'bg-green-100 text-green-800';
                default:
                    return 'bg-gray-100 text-gray-800';
            }
        }
    };
}
