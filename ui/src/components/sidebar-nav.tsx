"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brain, Gauge, Settings2, ShieldCheck, Sword } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Home", icon: Gauge },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/armory", label: "Armory", icon: Sword },
  { href: "/automation", label: "Branch", icon: ShieldCheck },
  { href: "/settings", label: "Control", icon: Settings2 },
];

export default function SidebarNav({ compact = false }) {
  const pathname = usePathname();

  const getLinkClass = (href) =>
    cn(
      "flex items-center gap-3 rounded-2xl border px-3 py-2.5 text-sm font-bold tracking-tight transition-colors",
      pathname === href
        ? "border-[#42A5F5]/40 bg-[#42A5F5]/20 text-[#1F5D93]"
        : "border-transparent text-blue-900/60 hover:border-white hover:bg-white/70 hover:text-slate-900",
    );

  return (
    <nav className={compact ? "mt-4 grid grid-cols-2 gap-2" : "flex-1 space-y-1.5 p-4"}>
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <Link key={item.href} href={item.href} className={getLinkClass(item.href)}>
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}