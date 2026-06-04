import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import './index.css'
import { router } from './routes/router'
import { SseProvider } from './lib/events'

async function bootstrap() {
  if (import.meta.env.VITE_API_MOCKING === 'true') {
    const { worker } = await import('./mock/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <SseProvider>
        <RouterProvider router={router} />
      </SseProvider>
    </StrictMode>,
  )
}

bootstrap().catch((err) => console.error(err))
