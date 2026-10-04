import { StrictMode, Component, ErrorInfo, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('React Error Boundary caught:', error, errorInfo)
    // Also show error in DOM
    document.body.innerHTML = `
      <div style="padding: 20px; color: red; font-family: monospace; max-width: 800px; margin: 20px auto;">
        <h2>React Error Boundary Caught:</h2>
        <pre style="white-space: pre-wrap; word-break: break-word; background: #1e1e1e; padding: 15px; border-radius: 4px;">
          ${error.message}
          <br /><br />
          ${error.stack}
        </pre>
      </div>
    `
  }

  render() {
    if (this.state.hasError) {
      return null // We already replaced document.body
    }

    return this.props.children
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)