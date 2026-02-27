import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-2xl text-sm font-bold tracking-tight ring-offset-background transition-[border-color,background-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "border border-[#42A5F5]/45 bg-[#42A5F5] text-white shadow-xl shadow-[#42A5F5]/35 hover:-translate-y-0.5 hover:bg-[#3b9be8]",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-[#42A5F5]/30 bg-[#42A5F5]/14 text-[#1F5D93] shadow-lg shadow-[#42A5F5]/20 hover:bg-[#42A5F5]/24",
        secondary:
          "border border-[#42A5F5]/22 bg-white/70 text-slate-900 shadow-lg shadow-blue-900/10 hover:bg-white/90",
        ghost: "text-blue-900/60 hover:bg-[#42A5F5]/14 hover:text-slate-900",
        link: "text-[#1F5D93] underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-xl px-3",
        lg: "h-11 rounded-xl px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }