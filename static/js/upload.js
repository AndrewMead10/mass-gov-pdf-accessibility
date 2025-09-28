function uploadHandler() {
    return {
        files: [],
        dragover: false,
        uploading: false,
        uploadProgress: [],

        handleDrop(event) {
            this.dragover = false;
            const droppedFiles = Array.from(event.dataTransfer.files);
            this.addFiles(droppedFiles);
        },

        handleFileSelect(event) {
            const selectedFiles = Array.from(event.target.files);
            this.addFiles(selectedFiles);
        },

        addFiles(newFiles) {
            const pdfFiles = newFiles.filter(file => file.type === 'application/pdf');
            if (pdfFiles.length !== newFiles.length) {
                showNotification('Only PDF files are allowed', 'warning');
            }
            this.files = [...this.files, ...pdfFiles];
        },

        removeFile(index) {
            this.files.splice(index, 1);
        },

        clearFiles() {
            this.files = [];
            this.uploadProgress = [];
        },

        formatFileSize(bytes) {
            return formatFileSize(bytes);
        },

        async uploadFiles() {
            if (this.files.length === 0) {
                showNotification('Please select files to upload', 'warning');
                return;
            }

            this.uploading = true;
            this.uploadProgress = this.files.map(file => ({
                filename: file.name,
                status: 'Uploading...',
                percent: 0
            }));

            try {
                const formData = new FormData();
                this.files.forEach(file => {
                    formData.append('files', file);
                });

                // Update progress to show upload in progress
                this.uploadProgress.forEach(progress => {
                    progress.percent = 50;
                    progress.status = 'Processing...';
                });

                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Upload failed');
                }

                const uploadedDocuments = await response.json();

                // Update progress to complete
                this.uploadProgress.forEach((progress, index) => {
                    progress.percent = 100;
                    progress.status = 'Uploaded';
                });

                // Start processing each document
                for (const document of uploadedDocuments) {
                    try {
                        await fetch(`/api/process/${document.id}`, {
                            method: 'POST'
                        });
                    } catch (error) {
                        console.error(`Failed to start processing for document ${document.id}:`, error);
                    }
                }

                showNotification(`Successfully uploaded ${uploadedDocuments.length} files`, 'success');

                // Redirect to dashboard after a short delay
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 2000);

            } catch (error) {
                console.error('Upload failed:', error);
                showNotification(error.message || 'Upload failed', 'error');

                // Reset progress on error
                this.uploadProgress.forEach(progress => {
                    progress.percent = 0;
                    progress.status = 'Failed';
                });
            } finally {
                this.uploading = false;
            }
        }
    };
}