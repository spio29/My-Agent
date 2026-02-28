"use client";
import { useQuery } from "@tanstack/react-query";
import { getMemory } from "@/lib/api";

const formatMemoryValue = (value: unknown): string => {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

export default function MemoryPage() {
  const { data: memories = [] } = useQuery({
    queryKey: ["memory"],
    queryFn: getMemory,
  });

  return (
    <div style={{padding: "40px"}}>
      <h1>Memory Vault</h1>
      <ul>
        {memories.map((mem, i) => (
          <li key={i}>
            <b>{mem.key}</b>: {formatMemoryValue(mem.value)}
          </li>
        ))}
      </ul>
    </div>
  );
}
