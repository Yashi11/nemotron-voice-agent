// SPDX-FileCopyrightText: Copyright (c) 2024–2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: BSD-2-Clause

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: "/",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7875",
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: ["import"],
      },
    },
  },
})
