#!/usr/bin/env python
"""清理 Redis 中的所有 Celery 任务"""

import redis
from app.config import settings

def clear_all_tasks():
    """清除所有 Celery 任务和队列"""
    try:
        # 连接 Redis
        r = redis.from_url(settings.redis_url)

        # 1. 清空 Celery 队列
        queue_keys = ['celery', 'celery:default']
        for key in queue_keys:
            deleted = r.delete(key)
            if deleted:
                print(f'✓ 清空队列: {key}')

        # 2. 删除所有任务结果
        task_keys = r.keys('celery-task-meta-*')
        if task_keys:
            r.delete(*task_keys)
            print(f'✓ 删除 {len(task_keys)} 个任务结果')
        else:
            print('✓ 没有待清理的任务')

        # 3. 清空其他 Celery 相关的 keys
        other_keys = r.keys('_kombu.*') + r.keys('unacked*')
        if other_keys:
            r.delete(*other_keys)
            print(f'✓ 清理 {len(other_keys)} 个其他键')

        print('\n✅ 所有旧任务已清理完成')

    except Exception as e:
        print(f'❌ 清理失败: {e}')
        return False

    return True

if __name__ == '__main__':
    clear_all_tasks()
