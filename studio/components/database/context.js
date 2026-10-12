'use client'

import { createContext, useContext } from 'react'

/** What every database page can reach: the project's connections, the rows drawer, and the other pages. */
export const Db = createContext({ context: {}, openRows: () => {}, go: () => {} })
export const useDatabase = () => useContext(Db)
