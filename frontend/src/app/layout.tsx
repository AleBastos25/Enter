import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PDF Extractor UI',
  description: 'UI para extração de dados de PDFs usando PDF Extractor',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="bg-[#000000] text-white antialiased">{children}</body>
    </html>
  )
}

