import styles from './App.module.css'
import { ChatPane } from './components/ChatPane.tsx'
import { Sidebar } from './components/Sidebar.tsx'
import { SourcePanel } from './components/SourcePanel.tsx'
import { useChatStore } from './store.ts'

export default function App() {
  const panelOpen = useChatStore((state) => state.activeCitation !== null)

  return (
    <div className={styles.layout} data-panel={panelOpen}>
      <Sidebar />
      <ChatPane />
      <SourcePanel />
    </div>
  )
}
