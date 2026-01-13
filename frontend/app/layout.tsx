import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from './providers'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'SnapPlan - Blueprint Quantity Takeoff',
  description: 'Turn blueprints into quantities. Extract doors, flooring, drywall, and more from construction PDFs.',
  keywords: ['construction', 'blueprint', 'takeoff', 'doors', 'flooring', 'drywall', 'measurement'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
