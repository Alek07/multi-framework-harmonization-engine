import { createFileRoute } from '@tanstack/react-router'

import { Composer } from '../features/composition/Composer'

export const Route = createFileRoute('/composer')({ component: Composer })
