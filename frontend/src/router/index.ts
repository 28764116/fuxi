import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Projects from '../views/Projects.vue'
import LiveGraphBuilder from '../views/LiveGraphBuilder.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: Home,
  },
  {
    path: '/projects',
    name: 'projects',
    component: Projects,
  },
  {
    path: '/project/:id',
    name: 'project',
    component: LiveGraphBuilder,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
