import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import './index.css'
import { router } from './routes/router'
import { SseProvider } from './lib/events'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <SseProvider>
      <RouterProvider router={router} />
    </SseProvider>
  </StrictMode>,
)
