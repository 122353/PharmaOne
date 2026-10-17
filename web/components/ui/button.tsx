import * as React from 'react';
import {Slot} from '@radix-ui/react-slot';
import {cva,type VariantProps} from 'class-variance-authority';
import {cn} from '@/lib/utils';

const buttonVariants=cva('inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:pointer-events-none disabled:opacity-50',{variants:{variant:{default:'bg-[#11695D] text-white hover:bg-[#0B4B44]',outline:'border border-[#A8CFC2] bg-white text-[#11695D] hover:bg-[#E8F5F1]'},size:{default:'h-10 px-4 py-2',sm:'h-9 px-3',lg:'h-11 px-6'}},defaultVariants:{variant:'default',size:'default'}});

function Button({className,variant,size,asChild=false,...props}:React.ComponentProps<'button'>&VariantProps<typeof buttonVariants>&{asChild?:boolean}){
  const Comp=asChild?Slot:'button';
  return <Comp data-slot="button" className={cn(buttonVariants({variant,size,className}))} {...props}/>;
}
export {Button,buttonVariants};
