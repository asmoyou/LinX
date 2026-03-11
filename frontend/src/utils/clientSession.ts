import { resetAllStores } from '../stores';

export const clearClientSession = (): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('refresh_token');
  }

  resetAllStores();
};
