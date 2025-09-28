// Utility functions used across the application

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API request failed');
        }

        return await response.json();
    } catch (error) {
        console.error('API call failed:', error);
        throw error;
    }
}

function showNotification(message, type = 'info') {
    // Simple notification system - could be enhanced with a proper toast library
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 p-4 rounded-md z-50 ${getNotificationClass(type)}`;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 5000);
}

function getNotificationClass(type) {
    switch (type) {
        case 'success':
            return 'bg-green-100 border border-green-400 text-green-700';
        case 'error':
            return 'bg-red-100 border border-red-400 text-red-700';
        case 'warning':
            return 'bg-yellow-100 border border-yellow-400 text-yellow-700';
        default:
            return 'bg-blue-100 border border-blue-400 text-blue-700';
    }
}