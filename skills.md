# Frontend Skills

Reusable patterns, components, and architecture decisions extracted from this project. Use this as a blueprint to reconstruct the frontend for any multi-agent AI application.

---

## Tech Stack

| Layer | Choice | Version |
|---|---|---|
| Framework | React + TypeScript | 18.2 / 5.3 |
| Build tool | Vite | 5.0 |
| Canvas / graph | @xyflow/react (ReactFlow v12) | 12.5 |
| Styling | Tailwind CSS + shadcn/ui (new-york style) | 3.4 |
| Theme | next-themes | 0.4 |
| Icons | lucide-react | 0.507 |
| Toasts | sonner | 2.0 |
| Modals / primitives | Radix UI (accordion, dialog, popover, tabs, tooltip) | various |
| Command palette | cmdk | 1.1 |
| Syntax highlighting | react-syntax-highlighter (Prism + vscDarkPlus) | 15.6 |

---

## Project Structure

```
app/frontend/
├── index.html                   # Single root div #root
├── vite.config.ts               # @ alias → ./src, @vitejs/plugin-react
├── tailwind.config.ts           # Extends CSS vars into Tailwind tokens
├── postcss.config.mjs           # tailwindcss + autoprefixer
├── components.json              # shadcn config: style=new-york, cssVariables=true
└── src/
    ├── main.tsx                 # Mount: ThemeProvider > NodeProvider > App
    ├── App.tsx                  # Renders <Layout /> + <Toaster />
    ├── index.css                # CSS custom properties (design tokens), animations
    ├── components/
    │   ├── layout/              # Layout, TopBar, LeftSidebar, RightSidebar, BottomPanel
    │   ├── tabs/                # TabBar, TabContent, TabItem
    │   ├── panels/              # bottom panel tabs (OutputTab, BacktestOutput, etc.)
    │   ├── settings/            # Settings page (ApiKeys, etc.)
    │   └── ui/                  # shadcn primitives + custom: LlmSelector, NodeShell
    ├── contexts/                # NodeContext, FlowContext, TabsContext, LayoutContext
    ├── providers/               # ThemeProvider (wraps next-themes)
    ├── hooks/                   # useNodeState, useFlowConnection, useResizable, etc.
    ├── services/                # api.ts, flow-service.ts, backtest-api.ts, api-keys-api.ts
    ├── nodes/                   # ReactFlow node type definitions + node components
    ├── edges/                   # ReactFlow edge type definitions
    ├── types/                   # Shared TypeScript interfaces
    ├── data/                    # Static/cached data (agents list, models list, node mappings)
    ├── utils/                   # Pure helpers: date formatting, text, output color/icon utils
    └── lib/
        └── utils.ts             # cn(), isMac(), formatKeyboardShortcut(), getProviderColor()
```

---

## 1. Entry Point and Provider Stack

`main.tsx` wraps the app in providers from outermost to innermost:

```tsx
// src/main.tsx
createRoot(document.getElementById('root')!).render(
  <ThemeProvider defaultTheme="dark" storageKey="theme">
    <NodeProvider>          {/* global agent execution state */}
      <App />
    </NodeProvider>
  </ThemeProvider>
)
```

`App.tsx` adds layout-level providers:

```tsx
// src/App.tsx
export default function App() {
  return (
    <TabsProvider>
      <LayoutProvider>
        <Layout />
        <Toaster position="top-right" richColors />
      </LayoutProvider>
    </TabsProvider>
  )
}
```

`Layout.tsx` adds canvas-level providers:

```tsx
// src/components/layout/Layout.tsx
<FlowProvider>
  <ReactFlowProvider>
    <SidebarProvider>
      {/* TopBar, TabBar, LeftSidebar, RightSidebar, TabContent, BottomPanel */}
    </SidebarProvider>
  </ReactFlowProvider>
</FlowProvider>
```

---

## 2. Routing — Custom Tab System (No URL Router)

There are no URL routes. Navigation is a multi-tab system backed by localStorage.

### Tab Context

```tsx
// src/contexts/tabs-context.tsx
interface Tab {
  id: string
  type: 'flow' | 'settings'
  title: string
  content: React.ReactNode   // JSX — not serialized to localStorage
}

interface TabsContextType {
  tabs: Tab[]
  activeTabId: string | null
  addTab: (tab: Tab) => void
  removeTab: (id: string) => void
  setActiveTab: (id: string) => void
  updateTab: (id: string, updates: Partial<Tab>) => void
}
```

### Persistence

Tabs are serialized to localStorage without their JSX content. On restore, `TabService.restoreTab()` uses `React.createElement` to reconstruct content:

```ts
// src/services/tab-service.ts
static restoreTab(tab: SerializedTab): Tab {
  switch (tab.type) {
    case 'flow':
      return { ...tab, content: createElement(FlowTabContent, { flowId: tab.flowId }) }
    case 'settings':
      return { ...tab, content: createElement(Settings, {}) }
  }
}
```

### Tab Bar

- Draggable tabs via HTML5 `draggable` + `onDragStart`/`onDrop`
- Active tab renders `TabContent` which renders `activeTab.content` as JSX
- New tabs open via `addTab()` with a fresh JSX node

---

## 3. State Management

No Redux, Zustand, or Jotai. All state uses React Context + module-level singleton managers.

### Context Inventory

| Context | Responsibility |
|---|---|
| `NodeContext` | Per-flow agent execution state — node statuses, message history, output data, model selections |
| `FlowContext` | ReactFlow canvas operations — save/load/create flow, `currentFlowId`, `isUnsaved` flag |
| `TabsContext` | Multi-tab lifecycle — open, close, switch, persist |
| `LayoutContext` | Bottom panel collapsed state, sidebar widths |

### NodeContext Shape

```tsx
// src/contexts/node-context.tsx
interface NodeContextType {
  // Keyed by "flowId:nodeId"
  agentNodeData: Record<string, AgentNodeData>
  outputData: Record<string, OutputData>
  nodeModelSelections: Record<string, { modelName: string; modelProvider: string }>

  updateAgentNode: (flowId: string, nodeId: string, data: Partial<AgentNodeData>) => void
  updateAgentNodes: (flowId: string, nodeIds: string[], status: AgentStatus) => void
  resetAllNodes: (flowId: string) => void
  setOutputNodeData: (flowId: string, data: OutputData) => void
}
```

### Module-Level Singleton Managers

These are not React state — they are class instances exported from hook files and act as global stores with listener-based reactivity.

**FlowStateManager** (`hooks/use-node-state.ts`) — persists node form input values across tab switches:

```ts
const stateMap = new Map<string, Record<string, any>>()  // key: "flowId:nodeId"
const listeners = new Set<() => void>()

export function getNodeInternalState(flowId: string, nodeId: string) { ... }
export function setNodeInternalState(flowId: string, nodeId: string, key: string, value: any) { ... }
export function setCurrentFlowId(id: string) { ... }
```

**FlowConnectionManager** (`hooks/use-flow-connection.ts`) — tracks active SSE connections per flow:

```ts
interface FlowConnectionState {
  status: 'idle' | 'connecting' | 'connected' | 'error' | 'completed'
  abortController: AbortController | null
  startTime: number | null
  endTime: number | null
}

const connections = new Map<string, FlowConnectionState>()
const listeners = new Set<() => void>()
```

---

## 4. `useNodeState` — Persistent Node Form State

Drop-in replacement for `useState` that survives tab switches and flow saves:

```ts
// src/hooks/use-node-state.ts
function useNodeState<T>(nodeId: string, stateKey: string, defaultValue: T): [T, (val: T) => void]
```

Usage inside any node component:

```tsx
const [tickers, setTickers] = useNodeState(id, 'tickers', '')
const [initialCash, setInitialCash] = useNodeState(id, 'initialCash', 100000)
const [modelName, setModelName] = useNodeState(id, 'modelName', 'gpt-4.1')
```

The hook reads from `FlowStateManager` on mount, writes back on every set, and re-renders when the current flow changes.

---

## 5. `useFlowConnection` — SSE Lifecycle Hook

```ts
// src/hooks/use-flow-connection.ts
function useFlowConnection(flowId: string): {
  isConnecting: boolean
  isConnected: boolean
  isProcessing: boolean
  canRun: boolean
  runFlow: (params: RunParams) => Promise<void>
  runBacktest: (params: BacktestParams) => Promise<void>
  stopFlow: () => void
  recoverFlowState: () => void
}
```

Internally:
1. Calls `api.runHedgeFund()` or `backtestApi.runBacktest()`
2. Dispatches SSE events to `NodeContext` (`updateAgentNode`, `setOutputNodeData`, etc.)
3. Manages `FlowConnectionManager` state (idle → connecting → connected → completed/error)
4. Schedules cleanup after 30 seconds on completion

---

## 6. API Communication

### Base URL

```ts
// src/services/api.ts
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
```

### Standard REST Pattern

```ts
// GET
const response = await fetch(`${API_BASE_URL}/flows/`)
const data = await response.json()

// POST
const response = await fetch(`${API_BASE_URL}/flows/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})
```

### SSE Streaming Pattern

Used for long-running agent runs. The server sends `text/event-stream` in response to a POST body.

```ts
// src/services/api.ts — core SSE parsing loop
async function streamSSE(url: string, body: object, handlers: SSEHandlers) {
  const controller = new AbortController()

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''           // keep incomplete last chunk

    for (const event of events) {
      const eventType = /^event: (.+)$/m.exec(event)?.[1]
      const dataStr = /^data: (.+)$/m.exec(event)?.[1]
      if (!eventType || !dataStr) continue

      const data = JSON.parse(dataStr)
      handlers[eventType]?.(data)         // 'start' | 'progress' | 'complete' | 'error'
    }
  }

  return () => controller.abort()         // returns stop function
}
```

### SSE Event Types

```ts
// Hedge fund run events
type SSEEvent =
  | { type: 'start' }
  | { type: 'progress'; agent: string; ticker: string; message: string; analysis?: string; status: AgentStatus }
  | { type: 'complete'; data: OutputData }
  | { type: 'error'; message: string }
```

---

## 7. ReactFlow Canvas

### Node Type Registration

```tsx
// src/nodes/index.ts
export const nodeTypes: NodeTypes = {
  stockAnalyzer:   StockAnalyzerNode,
  portfolioStart:  PortfolioStartNode,
  analyst:         AgentNode,
  output:          OutputNode,
  // add new types here
}

// src/Flow.tsx
<ReactFlow
  nodeTypes={nodeTypes}
  edgeTypes={edgeTypes}
  colorMode={theme === 'dark' ? 'dark' : 'light'}
  defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed } }}
>
  <Background variant={BackgroundVariant.Dots} />
</ReactFlow>
```

### NodeShell — Shared Node Wrapper

Every node is wrapped in `NodeShell` which provides:
- Left and right `<Handle>` connection points
- Card header with icon + display name
- Animated gradient border when `status === 'IN_PROGRESS'`
- Selected-state border highlight

```tsx
// src/components/ui/node-shell.tsx
interface NodeShellProps {
  id: string
  icon: React.ReactNode
  label: string
  status?: AgentStatus
  selected?: boolean
  width?: string          // Tailwind width class, default 'w-64'
  children: React.ReactNode
}
```

Usage:

```tsx
// Inside any node component
export function AgentNode({ id, data, selected }: NodeProps) {
  const nodeData = agentNodeData[id]

  return (
    <NodeShell id={id} icon={<Bot />} label={data.display_name} status={nodeData?.status} selected={selected}>
      {/* node body content */}
    </NodeShell>
  )
}
```

### IN_PROGRESS Animation

Applied via CSS classes when `status === 'IN_PROGRESS'`:

```css
/* src/index.css */
.node-in-progress {
  border: none !important;      /* hide static border */
}

.animated-border-container::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899, #6366f1);
  background-size: 200%;
  animation: gradient-shift 3s linear infinite;
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  z-index: -1;
}

.gradient-animation {
  background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899, #6366f1);
  background-size: 200%;
  animation: gradient-shift 3s linear infinite;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

---

## 8. Styling System

### Design Tokens (CSS Custom Properties)

All colors are HSL variables defined in `src/index.css` at `:root` (light) and `.dark`:

```css
:root {
  /* shadcn standard */
  --background: 0 0% 100%;
  --foreground: 0 0% 3.9%;
  --card: 0 0% 100%;
  --primary: 0 0% 9%;
  --muted: 0 0% 96.1%;
  --muted-foreground: 0 0% 45.1%;
  --border: 0 0% 89.8%;
  --radius: 0.5rem;

  /* project-specific */
  --panel-bg: 0 0% 97%;
  --node-bg: 0 0% 100%;
  --node-border: 0 0% 89.8%;
  --node-border-hover: 0 0% 75%;
  --node-border-selected: 221 83% 53%;
  --status-border: 0 0% 89.8%;
  --tab-active-bg: 0 0% 100%;
  --tab-inactive-bg: 0 0% 94%;
  --ramp-grey-100: 0 0% 97%;
  /* ... through --ramp-grey-1000 */
}
```

### Tailwind Config Extension

Map all CSS vars into Tailwind color tokens:

```ts
// tailwind.config.ts
theme: {
  extend: {
    colors: {
      background:  'hsl(var(--background))',
      foreground:  'hsl(var(--foreground))',
      panel:       'hsl(var(--panel-bg))',
      node: {
        DEFAULT:  'hsl(var(--node-bg))',
        border:   'hsl(var(--node-border))',
        hover:    'hsl(var(--node-border-hover))',
        selected: 'hsl(var(--node-border-selected))',
      },
      'ramp-grey': {
        100:  'hsl(var(--ramp-grey-100))',
        // ...
        1000: 'hsl(var(--ramp-grey-1000))',
      },
    },
    fontSize: {
      title:    ['0.875rem', { lineHeight: '1.25rem' }],
      subtitle: ['0.625rem', { lineHeight: '1rem' }],
    },
  }
}
```

### Utility Classes (Tailwind `@layer utilities`)

```css
@layer utilities {
  .bg-node       { background-color: hsl(var(--node-bg)); }
  .border-node   { border-color: hsl(var(--node-border)); }
  .border-node-hover { border-color: hsl(var(--node-border-hover)); }
  .border-node-selected { border-color: hsl(var(--node-border-selected)); }
  .hover-bg      { background-color: hsl(var(--hover-background)); }
  .hover-item    { @apply hover:hover-bg hover:hover-text cursor-pointer; }
  .active-item   { @apply active-bg active-text; }
}
```

### `cn()` Utility

```ts
// src/lib/utils.ts
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

Use everywhere: `cn('base-class', condition && 'conditional-class', props.className)`

---

## 9. Theme System

```tsx
// src/providers/theme-provider.tsx
import { ThemeProvider as NextThemesProvider } from 'next-themes'

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"           // applies .dark class to <html>
      defaultTheme="dark"
      storageKey="theme"          // localStorage key
      enableSystem                // respects OS preference
    >
      {children}
    </NextThemesProvider>
  )
}
```

Toggle:

```tsx
import { useTheme } from 'next-themes'
const { theme, setTheme } = useTheme()
```

---

## 10. Component Patterns

### Resizable Sidebars

```ts
// src/hooks/use-resizable.ts
function useResizable(options: {
  defaultWidth: number
  minWidth: number
  maxWidth: number
  side: 'left' | 'right' | 'bottom'
  storageKey?: string
}): {
  width: number
  isResizing: boolean
  handleMouseDown: (e: React.MouseEvent) => void
}
```

A drag handle `<div>` calls `handleMouseDown`. The hook attaches `mousemove`/`mouseup` to `document` and computes new width from `clientX`/`clientY`. Width is persisted to `localStorage` if `storageKey` is provided.

### Accordion Sidebar Lists

Both the left (flow list) and right (component palette) sidebars use shadcn `<Accordion>` with this pattern:

```tsx
<Accordion type="multiple" defaultValue={['group-1', 'group-2']}>
  {groups.map(group => (
    <AccordionItem key={group.id} value={group.id}>
      <AccordionTrigger className="px-3 py-2 text-xs font-medium uppercase tracking-wider">
        {group.label}
      </AccordionTrigger>
      <AccordionContent>
        {group.items.map(item => <ItemCard key={item.id} {...item} />)}
      </AccordionContent>
    </AccordionItem>
  ))}
</Accordion>
```

### Searchable Dropdown (Model / Run Mode Selector)

Uses shadcn `<Popover>` + `<Command>`:

```tsx
// src/components/ui/llm-selector.tsx
<Popover open={open} onOpenChange={setOpen}>
  <PopoverTrigger asChild>
    <Button variant="outline" role="combobox">
      {selectedModel?.display_name ?? 'Select model'}
    </Button>
  </PopoverTrigger>
  <PopoverContent>
    <Command>
      <CommandInput placeholder="Search models..." />
      <CommandList>
        {models.map(model => (
          <CommandItem
            key={model.model_name}
            value={model.display_name}
            onSelect={() => { onSelect(model); setOpen(false) }}
          >
            <span>{model.display_name}</span>
            <Badge>{model.provider}</Badge>
            <code className="ml-auto text-xs text-muted-foreground">{model.model_name}</code>
          </CommandItem>
        ))}
      </CommandList>
    </Command>
  </PopoverContent>
</Popover>
```

### Dialog Pattern

```tsx
<Dialog open={open} onOpenChange={setOpen}>
  <DialogContent className="max-w-4xl h-[80vh] flex flex-col">
    <DialogHeader>
      <DialogTitle>Agent Output — {ticker}</DialogTitle>
    </DialogHeader>
    <div className="flex-1 grid grid-cols-2 gap-4 overflow-hidden">
      <ActivityLog messages={messages} />
      <AnalysisPanel analysis={analysis} />
    </div>
  </DialogContent>
</Dialog>
```

### Keyboard Shortcuts

```ts
// src/hooks/use-keyboard-shortcuts.ts
useKeyboardShortcuts({
  shortcuts: [
    { key: 's', meta: true, handler: handleSave },
    { key: 'z', meta: true, handler: handleUndo },
    { key: 'z', meta: true, shift: true, handler: handleRedo },
  ]
})
```

Attaches `keydown` to `document`, checks `isMac()` to swap `metaKey`/`ctrlKey`.

---

## 11. Forms and Inputs

All forms are **fully controlled** — no `react-hook-form`. Node form state uses `useNodeState` instead of `useState`.

### Numeric Input with Formatting

```tsx
<div className="relative">
  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
  <Input
    className="pl-7"
    value={initialCash.toLocaleString('en-US')}
    onChange={e => setInitialCash(Number(e.target.value.replace(/[^0-9.]/g, '')))}
  />
</div>
```

### Dynamic Array of Inputs (Portfolio Positions)

```tsx
{positions.map((pos, idx) => (
  <div key={idx} className="flex gap-2 items-center">
    <Input placeholder="Ticker" value={pos.ticker} onChange={e => updatePosition(idx, 'ticker', e.target.value)} />
    <Input placeholder="Qty" type="number" value={pos.quantity} onChange={e => updatePosition(idx, 'quantity', Number(e.target.value))} />
    {positions.length > 1 && (
      <Button variant="ghost" size="icon" onClick={() => removePosition(idx)}>
        <X className="h-4 w-4" />
      </Button>
    )}
  </div>
))}
<Button variant="outline" size="sm" onClick={addPosition}>
  <Plus className="h-3 w-3 mr-1" /> Add Position
</Button>
```

### Password Field with Toggle

```tsx
const [visible, setVisible] = useState(false)
<div className="relative">
  <Input type={visible ? 'text' : 'password'} value={value} onChange={e => onChange(e.target.value)} />
  <Button
    variant="ghost" size="icon"
    className="absolute right-8 top-1/2 -translate-y-1/2"
    onClick={() => setVisible(v => !v)}
  >
    {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
  </Button>
  <Button variant="ghost" size="icon" className="absolute right-0 top-1/2 -translate-y-1/2" onClick={onClear}>
    <X className="h-4 w-4" />
  </Button>
</div>
```

---

## 12. Real-Time / Streaming UI

### Polling Trigger for Output Panel

The output panel reads from `NodeContext` (not a stream directly) and forces re-renders via polling:

```tsx
// src/components/panels/bottom/tabs/output-tab.tsx
const [, setUpdateTrigger] = useState(0)

useEffect(() => {
  const interval = setInterval(() => setUpdateTrigger(n => n + 1), 1000)
  return () => clearInterval(interval)
}, [])
```

### Agent Progress List

```tsx
{agents.map(agent => (
  <div key={agent.id} className="flex items-center gap-3 py-2">
    <StatusIcon status={agent.status} />                {/* CheckCircle / XCircle / MoreHorizontal / Clock */}
    <div className="flex-1 min-w-0">
      <p className="text-sm font-medium truncate">{agent.displayName}</p>
      {agent.ticker && <p className="text-xs text-muted-foreground">{agent.ticker}</p>}
      {agent.message && <p className="text-xs text-muted-foreground truncate">{agent.message}</p>}
    </div>
    {agent.timestamp && <span className="text-xs text-muted-foreground">{formatTime(agent.timestamp)}</span>}
  </div>
))}
```

### Status Icon Helper

```tsx
function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case 'COMPLETE':     return <CheckCircle className="h-4 w-4 text-green-500" />
    case 'ERROR':        return <XCircle className="h-4 w-4 text-red-500" />
    case 'IN_PROGRESS':  return <MoreHorizontal className="h-4 w-4 text-yellow-500" />
    default:             return <Clock className="h-4 w-4 text-muted-foreground" />
  }
}
```

---

## 13. Data Display Patterns

### Signal / Action Color Coding

```ts
// src/utils/output-tab-utils.ts
export function getSignalColor(signal: string): string {
  if (signal === 'bullish') return 'text-green-500'
  if (signal === 'bearish') return 'text-red-500'
  return 'text-primary'
}

export function getActionColor(action: string): string {
  if (['buy', 'cover'].includes(action.toLowerCase())) return 'text-green-500'
  if (['sell', 'short'].includes(action.toLowerCase())) return 'text-red-500'
  return 'text-primary'
}
```

### Standard Results Table

```tsx
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Ticker</TableHead>
      <TableHead>Action</TableHead>
      <TableHead>Confidence</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {decisions.map(d => (
      <TableRow key={d.ticker}>
        <TableCell className="font-mono font-medium">{d.ticker}</TableCell>
        <TableCell className={getActionColor(d.action)}>{d.action.toUpperCase()}</TableCell>
        <TableCell>{d.confidence}%</TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

### ReasoningContent — JSON vs Plain Text Detector

```tsx
// src/components/reasoning-content.tsx
function ReasoningContent({ content }: { content: string }) {
  const isJson = isJsonString(content)

  return (
    <div className="relative group">
      {isJson ? (
        <pre className="text-xs font-mono max-h-36 overflow-y-auto bg-muted rounded p-2">
          {JSON.stringify(JSON.parse(content), null, 2)}
        </pre>
      ) : (
        content.split('\n').filter(Boolean).map((para, i) => (
          <p key={i} className="text-xs text-muted-foreground mb-1">{para}</p>
        ))
      )}
      <CopyButton className="absolute top-1 right-1 opacity-0 group-hover:opacity-100" text={content} />
    </div>
  )
}
```

### Syntax-Highlighted JSON

```tsx
import SyntaxHighlighter from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

<SyntaxHighlighter language="json" style={vscDarkPlus} customStyle={{ borderRadius: '0.375rem', fontSize: '0.75rem' }}>
  {JSON.stringify(data, null, 2)}
</SyntaxHighlighter>
```

---

## 14. Undo / Redo

```ts
// src/hooks/use-flow-history.ts
function useFlowHistory(options: { maxSnapshots?: number; debounceMs?: number }) {
  const history = useRef<FlowSnapshot[]>([])
  const future = useRef<FlowSnapshot[]>([])

  const pushSnapshot = useMemo(
    () => debounce((nodes, edges) => {
      history.current.push({ nodes, edges, timestamp: Date.now() })
      if (history.current.length > (options.maxSnapshots ?? 50)) {
        history.current.shift()
      }
      future.current = []
    }, options.debounceMs ?? 500),
    []
  )

  function undo() { /* pop history, push to future, restore */ }
  function redo() { /* pop future, push to history, restore */ }

  return { pushSnapshot, undo, redo, canUndo, canRedo }
}
```

---

## 15. Toast Notifications

Wrap `sonner` with a deduplication layer:

```ts
// src/hooks/use-toast-manager.ts
const visibleToasts: Record<string, boolean> = {}

export function useToastManager() {
  function show(type: 'success' | 'error' | 'info', message: string, id?: string) {
    const toastId = id ?? message
    if (visibleToasts[toastId]) return

    visibleToasts[toastId] = true
    toast[type](message, {
      id: toastId,
      onDismiss: () => { delete visibleToasts[toastId] },
    })
  }

  return { showSuccess: (m, id?) => show('success', m, id), showError: (m, id?) => show('error', m, id) }
}
```

---

## 16. Vite Config

```ts
// vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
})
```

Environment variable: `VITE_API_URL=http://localhost:8000` in `.env`.

---

## 17. Key Libraries Reference

| Library | Import Path | Used For |
|---|---|---|
| `@xyflow/react` | `@xyflow/react` | Node graph canvas, handles, edges |
| `next-themes` | `next-themes` | Light/dark theme with OS sync |
| `lucide-react` | `lucide-react` | All icons (Bot, Brain, Play, Square, ChartLine, etc.) |
| `sonner` | `sonner` | Toast notifications |
| `cmdk` | `cmdk` | Searchable command/dropdown (`Command`, `CommandInput`, `CommandItem`) |
| `clsx` + `tailwind-merge` | — | `cn()` utility for conditional Tailwind classes |
| `class-variance-authority` | `class-variance-authority` | `cva()` for variant-based component APIs |
| `react-syntax-highlighter` | `react-syntax-highlighter` | JSON syntax highlighting in output dialogs |
| All `@radix-ui/*` | `@radix-ui/react-*` | Accordion, Dialog, Popover, Tabs, Tooltip, Checkbox, Separator |
| `@tailwindcss/typography` | plugin | Prose/markdown content styling |
| `tailwindcss-animate` | plugin | Accordion open/close animations |

---

## 18. shadcn/ui Setup

`components.json` config:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

Add components with: `npx shadcn@latest add button card input table tabs dialog accordion popover tooltip separator`

---

## 19. Fonts

Host fonts locally in `/public/fonts/` and load via `@font-face`:

```css
/* src/index.css */
@font-face {
  font-family: 'geist';
  src: url('/fonts/GeistVF.woff2') format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'geist-mono';
  src: url('/fonts/GeistMonoVF.woff2') format('woff2');
  font-display: swap;
}
```

---

## Quick-Start Checklist for a New Project

1. `npm create vite@latest my-app -- --template react-ts`
2. Install: `tailwindcss`, `@tailwindcss/typography`, `tailwindcss-animate`, `@vitejs/plugin-react`
3. Install: `@xyflow/react`, `next-themes`, `lucide-react`, `sonner`, `cmdk`, `clsx`, `tailwind-merge`, `class-variance-authority`
4. Install all `@radix-ui/react-*` packages needed
5. Run `npx shadcn@latest init` and add required components
6. Copy `src/index.css` (design tokens + animation classes)
7. Copy `tailwind.config.ts` (token mapping + custom sizes)
8. Copy `src/lib/utils.ts` (`cn()`)
9. Copy `src/providers/theme-provider.tsx`
10. Set up contexts: `NodeContext`, `TabsContext`, `LayoutContext`
11. Set up module singletons: `FlowStateManager`, `FlowConnectionManager`
12. Implement `useNodeState`, `useFlowConnection`, `useResizable`
13. Register ReactFlow `nodeTypes` and build `NodeShell` wrapper
14. Implement SSE streaming in `services/api.ts`
15. Add `VITE_API_URL` to `.env`
