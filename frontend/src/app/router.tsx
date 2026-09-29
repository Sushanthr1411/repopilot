import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { HomePage } from '../pages/HomePage'
import { RepositoryWorkspacePage } from '../pages/RepositoryWorkspacePage'

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/r/:repoId" element={<RepositoryWorkspacePage />} />
      </Routes>
    </BrowserRouter>
  )
}
