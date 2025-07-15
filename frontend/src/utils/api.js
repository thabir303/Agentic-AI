const API_BASE_URL = '/api';

// Helper function to get auth headers
const getAuthHeaders = () => {
  const token = localStorage.getItem('access_token');
  return {
    'Content-Type': 'application/json',
    ...(token && { 'Authorization': `Bearer ${token}` })
  };
};

// Auth API
export const authAPI = {
  login: async (credentials) => {
    const response = await fetch(`${API_BASE_URL}/auth/signin/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(credentials)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Login failed');
    }
    
    return { data: await response.json() };
  },

  register: async (userData) => {
    const response = await fetch(`${API_BASE_URL}/auth/signup/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(userData)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Registration failed');
    }
    
    return { data: await response.json() };
  },

  profile: async () => {
    const response = await fetch(`${API_BASE_URL}/auth/profile/`, {
      headers: getAuthHeaders()
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch profile');
    }
    
    return { data: await response.json() };
  }
};

// Products API
export const productsAPI = {
  getProducts: async (params = {}) => {
    const searchParams = new URLSearchParams(params);
    const response = await fetch(`${API_BASE_URL}/auth/products/?${searchParams}`, {
      headers: getAuthHeaders()
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch products');
    }
    
    return { data: await response.json() };
  },

  getProduct: async (id) => {
    const response = await fetch(`${API_BASE_URL}/auth/products/${id}/`, {
      headers: getAuthHeaders()
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch product');
    }
    
    return { data: await response.json() };
  }
};

// Chatbot API
export const chatbotAPI = {
  sendMessage: async (message) => {
    const response = await fetch(`${API_BASE_URL}/auth/chatbot/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ message })
    });
    
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    
    return { data: await response.json() };
  }
};

// Issues API
export const issuesAPI = {
  getIssues: async () => {
    const response = await fetch(`${API_BASE_URL}/auth/admin/issues/`, {
      headers: getAuthHeaders()
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch issues');
    }
    
    return { data: await response.json() };
  },

  resolveIssue: async (issueId) => {
    const response = await fetch(`${API_BASE_URL}/auth/admin/issues/${issueId}/`, {
      method: 'PATCH',
      headers: getAuthHeaders(),
      body: JSON.stringify({ status: 'resolved' })
    });
    
    if (!response.ok) {
      throw new Error('Failed to resolve issue');
    }
    
    return { data: await response.json() };
  },

  deleteIssue: async (issueId) => {
    const response = await fetch(`${API_BASE_URL}/auth/admin/issues/${issueId}/`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    });
    
    if (!response.ok) {
      throw new Error('Failed to delete issue');
    }
    
    return { data: await response.json() };
  }
};
