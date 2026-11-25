// Static React TSX fixture only. Never execute.
import React from 'react';
import { OrderBadge } from '@/components/OrderBadge';

export function OrderList(props: { note: string }) {
  fetch('/api/orders');
  return (
    <div>
      <OrderBadge label="Orders" />
      <div dangerouslySetInnerHTML={{ __html: props.note }} />
    </div>
  );
}
