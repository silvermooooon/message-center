import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ plugins: [react()], server: { proxy: { '/api': { target: process.env.MESSAGE_CENTER_API_URL || 'http://127.0.0.1:8020', changeOrigin: true }, '/health': { target: process.env.MESSAGE_CENTER_API_URL || 'http://127.0.0.1:8020', changeOrigin: true } } } });
