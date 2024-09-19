# region imports
from AlgorithmImports import *
# endregion
from QuantConnect import *
from QuantConnect.Algorithm import *
from QuantConnect.Algorithm.Framework import *

class ProtecOptions(RiskManagementModel):
    def SellCall(self):
        contracts = self.OptionChainProvider.GetOptionContractList(self.underlyingsymbol, self.Time)
        if len(contracts) == 0: return
        min_expiry = 0
        max_expiry = 40
        
        filtered_contracts = [i for i in contracts if min_expiry <= (i.ID.Date.date() - self.Time).days <= max_expiry]
        call = [x for x in filtered_contracts if x.ID.OptionRight == 0] 
        
        if len(call) == 0: return
        # sorted the contracts according to their expiration dates and choose the ATM options
        self.contract = sorted(sorted(call, key = lambda x: abs(self.Securities[self.syl].Price - x.ID.StrikePrice)), 
                                        key = lambda x: x.ID.Date, reverse=True)[0]
      
        self.AddOptionContract(self.contract, Resolution.Minute)
        self.MarketOrder(self.contract, -1)

    
    def BuyPut(self):
        contracts = self.OptionChainProvider.GetOptionContractList(self.underlyingsymbol, self.Time.date())
        if len(contracts) == 0: return
        min_expiry = 0
        max_expiry = 40
        
        filtered_contracts = [i for i in contracts if min_expiry <= (i.ID.Date.date() - self.Time.date()).days <= max_expiry]
        put = [x for x in filtered_contracts if x.ID.OptionRight == 1] 
        
        if len(put) == 0: return
        # sorted the contracts according to their expiration dates and choose the ATM options
        self.contract = sorted(sorted(put, key = lambda x: abs(self.Securities[self.syl].Price - x.ID.StrikePrice)), 
                                        key = lambda x: x.ID.Date, reverse=True)[0]
      
        self.AddOptionContract(self.contract, Resolution.Minute)
        self.MarketOrder(self.contract, 1)
