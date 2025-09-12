// Dashboard JavaScript functionality

// Load dashboard data on page load
document.addEventListener('DOMContentLoaded', function() {
    if (window.location.pathname === '/dashboard') {
        loadDashboard();
    }
});

// Main dashboard loading function
function loadDashboard() {
    loadStats();
    loadSubscriptions();
}

// Load statistics for dashboard cards
function loadStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-count').textContent = data.total || 0;
            document.getElementById('active-count').textContent = data.active || 0;
            document.getElementById('expiring-count').textContent = data.expiring_soon || 0;
            document.getElementById('expired-count').textContent = data.expired || 0;
        })
        .catch(error => {
            console.error('Error loading stats:', error);
            // Set default values on error
            document.getElementById('total-count').textContent = '0';
            document.getElementById('active-count').textContent = '0';
            document.getElementById('expiring-count').textContent = '0';
            document.getElementById('expired-count').textContent = '0';
        });
}

// Load subscriptions table
function loadSubscriptions() {
    fetch('/api/subscriptions')
        .then(response => response.json())
        .then(data => {
            const tbody = document.getElementById('subscriptions-table');
            
            if (data.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center py-4">
                            <div class="text-muted">
                                <h5>📋 No Subscriptions Found</h5>
                                <p>Click "Add Subscription" to get started</p>
                            </div>
                        </td>
                    </tr>
                `;
            } else {
                let tableHTML = '';
                
                data.forEach(subscription => {
                    const expiryDate = new Date(subscription.expiry);
                    const today = new Date();
                    const timeDiff = expiryDate - today;
                    const daysLeft = Math.ceil(timeDiff / (1000 * 60 * 60 * 24));
                    
                    let statusBadge = '';
                    let statusClass = '';
                    
                    if (daysLeft < 0) {
                        statusBadge = 'Expired';
                        statusClass = 'bg-danger';
                    } else if (daysLeft <= 3) {
                        statusBadge = 'Expiring Soon';
                        statusClass = 'bg-warning';
                    } else {
                        statusBadge = 'Active';
                        statusClass = 'bg-success';
                    }
                    
                    tableHTML += `
                        <tr>
                            <td><strong>${subscription.service}</strong></td>
                            <td>${subscription.username}</td>
                            <td>${subscription.email}</td>
                            <td>${subscription.expiry}</td>
                            <td>${daysLeft} days</td>
                            <td>${subscription.amount_received || 'N/A'}</td>
                            <td><span class="badge ${statusClass}">${statusBadge}</span></td>
                            <td>
                                <button class="btn btn-sm btn-outline-danger" onclick="deleteSubscription('${subscription.id}')">
                                    🗑️ Delete
                                </button>
                            </td>
                        </tr>
                    `;
                });
                
                tbody.innerHTML = tableHTML;
            }
        })
        .catch(error => {
            console.error('Error loading subscriptions:', error);
            const tbody = document.getElementById('subscriptions-table');
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center py-4">
                        <div class="text-danger">
                            <h5>❌ Error Loading Data</h5>
                            <p>Please try refreshing the page</p>
                        </div>
                    </td>
                </tr>
            `;
        });
}

// Add subscription function
function addSubscription() {
    const username = document.getElementById('username').value;
    const email = document.getElementById('email').value;
    const service = document.getElementById('service').value;
    const expiry = document.getElementById('expiry').value;
    const amount_received = document.getElementById('amount_received').value;
    const note = document.getElementById('note').value;
    
    if (!username || !email || !service || !expiry) {
        alert('Please fill in all required fields');
        return;
    }
    
    const subscriptionData = {
        username: username,
        email: email,
        service: service,
        expiry: expiry,
        amount_received: amount_received,
        note: note
    };
    
    fetch('/api/add-subscription', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(subscriptionData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('✅ Subscription added successfully!');
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('addModal'));
            modal.hide();
            
            // Reset form
            document.getElementById('addForm').reset();
            
            // Reload dashboard
            loadDashboard();
        } else {
            alert('❌ Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error adding subscription:', error);
        alert('❌ Error adding subscription. Please try again.');
    });
}

// Delete subscription function
function deleteSubscription(subscriptionId) {
    if (!confirm('Are you sure you want to delete this subscription?')) {
        return;
    }
    
    fetch(`/api/delete-subscription/${subscriptionId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('✅ Subscription deleted successfully!');
            loadDashboard();
        } else {
            alert('❌ Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error deleting subscription:', error);
        alert('❌ Error deleting subscription. Please try again.');
    });
}
