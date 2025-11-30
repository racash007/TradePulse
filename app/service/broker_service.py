from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import logging
from kiteconnect import KiteConnect


logger = logging.getLogger(__name__)


@dataclass
class BrokerConfig:
    """Configuration for the broker connection.

    Attributes:
        api_key: Kite Connect API key.
        access_token: Optional access token. If not provided, call generate_login_url
            and complete the login flow to obtain one.
        redirect_uri: Optional redirect URI used when generating login URL.
    """
    api_key: str
    access_token: Optional[str] = None
    redirect_uri: Optional[str] = None


class BrokerService:
    """Wrapper around KiteConnect to provide simple trading operations.

    This class keeps a KiteConnect client and exposes convenience methods with
    error handling and type hints. It intentionally avoids holding secrets in
    logs.
    """

    def __init__(self, config: BrokerConfig, timeout: int = 30) -> None:
        """Initialize the broker wrapper.

        Args:
            config: BrokerConfig dataclass with api_key and optional access_token.
            timeout: network timeout in seconds (if applicable).
        """
        self.config = config
        self.timeout = timeout
        self._client: Optional[KiteConnect] = None
        if KiteConnect is None:
            logger.warning("kiteconnect library not available; broker methods will fail if used")

        if self.config.access_token:
            try:
                self.connect()
            except Exception as exc:  # avoid raising during import; user can call connect
                logger.debug("Initial connect failed: %s", exc)

    # Connection / auth helpers
    def connect(self) -> None:
        """Create KiteConnect client and set access token if provided.

        Raises:
            RuntimeError: if kiteconnect library is not installed.
        """
        if KiteConnect is None:
            raise RuntimeError("kiteconnect library is required but not installed")

        self._client = KiteConnect(api_key=self.config.api_key)
        if self.config.access_token:
            # attach access token
            try:
                self._client.set_access_token(self.config.access_token)
            except Exception as exc:
                logger.exception("Failed to set access token: %s", exc)
                raise

    def generate_login_url(self) -> str:
        """Return the login URL where the user can obtain a request token.

        The redirect URI must be configured in the Kite developer console and
        optionally provided in the BrokerConfig. This method attempts to pass
        the redirect URI if supported by the installed kiteconnect version and
        falls back to calling without it.
        """
        if KiteConnect is None:
            raise RuntimeError("kiteconnect library is required but not installed")
        temp_client = KiteConnect(api_key=self.config.api_key)
        if not self.config.redirect_uri:
            return temp_client.login_url()
        # some versions accept redirect_uri as positional or keyword; try both
        try:
            # try positional first
            return temp_client.login_url(self.config.redirect_uri)
        except TypeError:
            try:
                return temp_client.login_url(redirect_uri=self.config.redirect_uri)  # type: ignore[arg-type]
            except Exception:
                # final fallback
                return temp_client.login_url()

    def _ensure_client(self) -> KiteConnect:
        """Ensure the KiteConnect client exists and return it.

        Raises:
            RuntimeError: if client is not connected yet.
        """
        if self._client is None:
            raise RuntimeError("KiteConnect client not initialized. Call connect() with a valid access token first.")
        return self._client

    # Market / account helpers
    def instruments(self, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return instruments list. Optionally filter by exchange.

        Args:
            exchange: optional exchange string (e.g., 'NSE').

        Returns:
            list of instrument dicts
        """
        client = self._ensure_client()
        try:
            instruments = client.instruments(exchange) if exchange else client.instruments()
            return instruments
        except Exception:
            logger.exception("Failed to fetch instruments")
            return []

    def get_positions(self) -> Dict[str, Any]:
        """Return current positions summary from Kite.

        Returns:
            Dict containing positions and net positions as provided by Kite.
        """
        client = self._ensure_client()
        try:
            return client.positions()
        except Exception:
            logger.exception("Failed to fetch positions")
            return {}

    def get_margin(self) -> Dict[str, Any]:
        """Return margin details for the account.

        Returns:
            margin information dictionary.
        """
        client = self._ensure_client()
        try:
            # kite.margins() returns overall; margins('equity') returns equity-specific on some versions
            try:
                return client.margins()
            except Exception:
                return client.margins('equity')
        except Exception:
            logger.exception("Failed to fetch margins")
            return {}

    # Order operations
    def place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = 'MARKET',
        product: str = 'MIS',
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: Optional[str] = None,
        variety: str = 'regular',
        **kwargs,
    ) -> Dict[str, Any]:
        """Place an order and return Kite's response.

        Args:
            tradingsymbol: symbol to trade (e.g., 'TCS').
            exchange: exchange string (e.g., 'NSE').
            transaction_type: 'BUY' or 'SELL'.
            quantity: integer number of shares.
            order_type: 'MARKET' or 'LIMIT' etc.
            product: product type like 'MIS', 'CNC', 'NRML'.
            price: price for LIMIT orders.
            trigger_price: trigger price for SL orders.
            validity: 'DAY' or 'IOC' etc.
            variety: order variety (default 'regular').
            kwargs: additional provider-specific fields.

        Returns:
            Kite place_order response dict.
        """
        client = self._ensure_client()
        payload: Dict[str, Any] = {
            'tradingsymbol': tradingsymbol,
            'exchange': exchange,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'order_type': order_type,
            'product': product,
            'variety': variety,
        }
        if price is not None:
            payload['price'] = float(price)
        if trigger_price is not None:
            payload['trigger_price'] = float(trigger_price)
        if validity is not None:
            payload['validity'] = validity
        payload.update(kwargs)

        try:
            response = client.place_order(**payload)
            return response
        except Exception:
            logger.exception("Failed to place order: %s", {k: payload.get(k) for k in ('tradingsymbol', 'exchange', 'transaction_type', 'quantity')})
            raise

    def modify_order(
        self,
        order_id: int,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Modify an existing order.

        Args:
            order_id: Kite order id to modify.
            quantity: new quantity (optional).
            price: new price (optional).
            trigger_price: new trigger price (optional).
            kwargs: provider-specific options.
        """
        client = self._ensure_client()
        payload: Dict[str, Any] = {'order_id': order_id}
        if quantity is not None:
            payload['quantity'] = int(quantity)
        if price is not None:
            payload['price'] = float(price)
        if trigger_price is not None:
            payload['trigger_price'] = float(trigger_price)
        payload.update(kwargs)

        try:
            return client.modify_order(**payload)
        except Exception:
            logger.exception("Failed to modify order %s", order_id)
            raise

    def cancel_order(self, order_id: int) -> Dict[str, Any]:
        """Cancel an order by id.

        Args:
            order_id: Kite order id.

        Returns:
            Kite's cancel_order response.
        """
        client = self._ensure_client()
        try:
            return client.cancel_order(order_id=order_id)
        except Exception:
            logger.exception("Failed to cancel order %s", order_id)
            raise

    def get_order_history(self, order_id: int) -> Dict[str, Any]:
        """Fetch order history for the given order id.

        Args:
            order_id: Kite order id.

        Returns:
            History dict as returned by Kite.
        """
        client = self._ensure_client()
        try:
            return client.order_history(order_id=order_id)
        except Exception:
            logger.exception("Failed to fetch order history for %s", order_id)
            return {}


# Backwards compatible alias for existing imports that used the lowercase name
broker_service = BrokerService
