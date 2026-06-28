"""
CPOE ↔ CPPT Synchronization Bridge
File: modules/bridge_cpoe_sync.py

FIXED: Sekarang query dari database (SQLite), bukan hanya session_state
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class CPOESyncManager:
    """Manager untuk sinkronisasi CPOE ke CPPT via database"""
    
    def __init__(self, db_path: str = "rsjpdhk_emr.db"):
        """Initialize dengan database path"""
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """Ensure CPOE tables exist"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Create CPOE orders table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cpoe_orders (
                        order_id TEXT PRIMARY KEY,
                        episode_id TEXT NOT NULL,
                        patient_no_rm TEXT,
                        order_type TEXT,
                        order_name TEXT,
                        order_content TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by TEXT
                    )
                """)
                
                conn.commit()
        except Exception as e:
            logger.warning(f"Error initializing CPOE tables: {e}")
    
    @contextmanager
    def _get_conn(self):
        """Context manager for database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def push_order_to_cppt(self, order_data: Dict) -> bool:
        """Push single order ke database"""
        try:
            required_fields = ["order_id", "episode_id", "order_type", "order_name"]
            if not all(field in order_data for field in required_fields):
                logger.warning(f"Missing required fields in order_data: {required_fields}")
                return False
            
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                # Check if order exists
                cursor.execute(
                    "SELECT order_id FROM cpoe_orders WHERE order_id = ?",
                    (order_data["order_id"],)
                )
                
                if cursor.fetchone():
                    # Update existing
                    cursor.execute("""
                        UPDATE cpoe_orders 
                        SET order_content = ?, status = ?, updated_at = ?, updated_by = ?
                        WHERE order_id = ?
                    """, (
                        order_data.get("order_content", ""),
                        order_data.get("status", "pending"),
                        datetime.now().isoformat(),
                        order_data.get("created_by", "system"),
                        order_data["order_id"]
                    ))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO cpoe_orders 
                        (order_id, episode_id, patient_no_rm, order_type, order_name, 
                         order_content, status, created_by, updated_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_data["order_id"],
                        order_data["episode_id"],
                        order_data.get("patient_no_rm", ""),
                        order_data["order_type"],
                        order_data["order_name"],
                        order_data.get("order_content", ""),
                        order_data.get("status", "pending"),
                        order_data.get("created_by", "system"),
                        order_data.get("created_by", "system")
                    ))
                
                conn.commit()
                return True
        
        except Exception as e:
            logger.error(f"Error pushing order to database: {e}")
            return False
    
    def get_cpoe_orders(self, episode_id: str) -> List[Dict]:
        """Get CPOE orders dari database untuk episode tertentu"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT order_id, episode_id, patient_no_rm, order_type, order_name, 
                           order_content, status, created_at, created_by, updated_at
                    FROM cpoe_orders
                    WHERE episode_id = ? AND status != 'cancelled'
                    ORDER BY created_at DESC
                """, (episode_id,))
                
                rows = cursor.fetchall()
                orders = [dict(row) for row in rows]
                
                return orders
        
        except Exception as e:
            logger.warning(f"Error getting CPOE orders: {e}")
            return []
    
    def update_order_status(self, episode_id: str, order_type: str = None, status: str = "integrated") -> bool:
        """Update order status di database"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                if order_type:
                    # Update specific order type untuk episode
                    cursor.execute("""
                        UPDATE cpoe_orders
                        SET status = ?, updated_at = ?
                        WHERE episode_id = ? AND order_type = ? AND status != 'cancelled'
                    """, (status, datetime.now().isoformat(), episode_id, order_type))
                else:
                    # Update semua order untuk episode
                    cursor.execute("""
                        UPDATE cpoe_orders
                        SET status = ?, updated_at = ?
                        WHERE episode_id = ? AND status != 'cancelled'
                    """, (status, datetime.now().isoformat(), episode_id))
                
                conn.commit()
                return cursor.rowcount > 0
        
        except Exception as e:
            logger.error(f"Error updating order status: {e}")
            return False
    
    def get_orders_by_episode(self, episode_id: str) -> List[Dict]:
        """Get orders untuk episode_id (alias untuk get_cpoe_orders)"""
        return self.get_cpoe_orders(episode_id)
    
    def get_orders_by_type(self, episode_id: str, order_type: str) -> List[Dict]:
        """Get orders untuk episode & type"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT order_id, episode_id, patient_no_rm, order_type, order_name, 
                           order_content, status, created_at, created_by
                    FROM cpoe_orders
                    WHERE episode_id = ? AND order_type = ? AND status != 'cancelled'
                    ORDER BY created_at DESC
                """, (episode_id, order_type))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        
        except Exception as e:
            logger.warning(f"Error getting orders by type: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE cpoe_orders
                    SET status = 'cancelled', updated_at = ?
                    WHERE order_id = ?
                """, (datetime.now().isoformat(), order_id))
                conn.commit()
                return cursor.rowcount > 0
        
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def get_sync_info(self, episode_id: str) -> Dict:
        """Get sync status untuk episode"""
        try:
            orders = self.get_cpoe_orders(episode_id)
            
            return {
                "total_orders": len(orders),
                "pending_orders": len([o for o in orders if o.get("status") == "pending"]),
                "integrated_orders": len([o for o in orders if o.get("status") == "integrated"]),
                "rejected_orders": len([o for o in orders if o.get("status") == "rejected"]),
                "last_sync_time": datetime.now().isoformat() if orders else None,
                "orders": orders
            }
        
        except Exception as e:
            logger.error(f"Error getting sync info: {e}")
            return {
                "total_orders": 0,
                "pending_orders": 0,
                "integrated_orders": 0,
                "rejected_orders": 0,
                "last_sync_time": None,
                "orders": []
            }