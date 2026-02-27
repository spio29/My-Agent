"use client";
import { useQuery } from "@tanstack/react-query";
import { getMemory } from "@/lib/api";

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
            <b>{mem.key}</b>: {mem.value}
          </li>
        ))}
      </ul>
    </div>
  );
}
