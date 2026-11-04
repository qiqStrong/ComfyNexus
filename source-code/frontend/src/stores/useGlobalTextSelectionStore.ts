import { create } from 'zustand'

interface GlobalTextSelectionState {
  visible: boolean
  active: boolean
  position: { x: number; y: number }
  setVisible: (visible: boolean) => void
  toggleActive: () => void
  setActive: (active: boolean) => void
  setPosition: (position: { x: number; y: number }) => void
  resetPosition: () => void
}

const STORAGE_KEY = 'comfyui-box-global-copy-button-position'

const getDefaultPosition = (): { x: number; y: number } => {
  if (typeof window !== 'undefined') {
    return {
      x: window.innerWidth - 50,
      y: window.innerHeight - 50
    }
  }
  return { x: 0, y: 0 }
}

const loadPositionFromStorage = (): { x: number; y: number } => {
  try {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed.x !== undefined && parsed.y !== undefined) {
          return { x: parsed.x, y: parsed.y }
        }
      }
    }
  } catch (error) {
    console.warn('[useGlobalTextSelectionStore] Failed to load position from storage:', error)
  }
  return getDefaultPosition()
}

export const useGlobalTextSelectionStore = create<GlobalTextSelectionState>((set) => ({
  visible: false,
  active: false,
  position: loadPositionFromStorage(),
  setVisible: (visible) => {
    set({ visible })
    if (!visible) {
      set({ active: false })
    }
  },
  toggleActive: () => set((state) => ({ active: !state.active })),
  setActive: (active) => set({ active }),
  setPosition: (position) => {
    set({ position })
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(position))
      }
    } catch (error) {
      console.warn('[useGlobalTextSelectionStore] Failed to save position to storage:', error)
    }
  },
  resetPosition: () => {
    const defaultPosition = getDefaultPosition()
    set({ position: defaultPosition })
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(defaultPosition))
      }
    } catch (error) {
      console.warn('[useGlobalTextSelectionStore] Failed to save position to storage:', error)
    }
  }
}))
