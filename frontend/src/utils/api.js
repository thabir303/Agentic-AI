import axios from 'axios';

// Create axios instance with base configuration
const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include JWT token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          const response = await axios.post('/api/auth/token/refresh/', {
            refresh: refreshToken,
          });

          const { access } = response.data;
          localStorage.setItem('access_token', access);

          // Retry the original request with new token
          originalRequest.headers.Authorization = `Bearer ${access}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed, redirect to login
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/auth';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Auth API calls
export const authAPI = {
  login: (credentials) => api.post('/auth/signin/', credentials),
  register: (userData) => api.post('/auth/signup/', userData),
  refreshToken: (refreshToken) => api.post('/auth/token/refresh/', { refresh: refreshToken }),
  profile: () => api.get('/auth/user/'),
};

// Products API calls
export const productsAPI = {
  getProducts: (params = {}) => api.get('/auth/products/', { params }),
  getProduct: (id) => api.get(`/auth/products/${id}/`),
  getCategories: () => api.get('/auth/categories/'),
  getSimilarProducts: (id) => api.get(`/auth/products/${id}/similar/`),
};

// Chatbot API calls
export const chatbotAPI = {
  sendMessage: (message) => api.post('/auth/chatbot/', { message }),
};

// Issues API calls (admin only)
export const issuesAPI = {
  getIssues: () => api.get('/auth/admin/issues/'),
  resolveIssue: (id) => api.patch(`/auth/admin/issues/${id}/`, { status: 'resolved' }),
  deleteIssue: (id) => api.delete(`/auth/admin/issues/${id}/`),
};

export default api;
