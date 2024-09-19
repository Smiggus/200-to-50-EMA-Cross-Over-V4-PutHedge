# region imports
from AlgorithmImports import *
# endregion
from riskManagement import * 
from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import *

class EMAMomentumUniverse(QCAlgorithm):
    
    def Initialize(self):
        self.SetStartDate(2011, 1, 1)
        #self.SetEndDate(2019, 4, 1)
        self.SetCash(250000)
        self.SetBenchmark("SPY")
        self.UniverseSettings.Resolution = Resolution.Daily
        #setting the coarse filter for investment universe
        self.AddUniverse(self.CoarseSelectionFunction) 
        self.equity = self.AddEquity("SPY", Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        # add VIX data
        self.vix = self.AddData(CBOE, "VIX").Symbol
        # initialize IV indicator
        self.rank = 0
        # initialize the option contract with empty string
        self.contract = str()
        self.contractsAdded = set()
        
        # parameters ------------------------------------------------------------
        self.DaysBeforeExp = 2 # number of days before expiry to exit
        self.DTE = 25 # target days till expiration
        self.OTM = 0.01 # target percentage OTM of put
        self.lookbackIV = 150 # lookback length of IV indicator
        self.IVlvl = 0.5 # enter position at this lvl of IV indicator
        self.percentage = 0.09 # percentage of portfolio for underlying asset
        self.options_alloc = 90 # 1 option for X num of shares (balanced would be 100)
        # ------------------------------------------------------------------------
    
        # schedule Plotting function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
        # schedule VIXRank function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.VIXRank)
        # warmup for IV indicator of data
        self.SetWarmUp(timedelta(self.lookbackIV)) 
        
        #declaring dictionary averages
        self.SetRiskManagement(MaximumDrawdownPercentPerSecurityCustom(0.10))
        #self.SetExecution(ImmediateExecutionModel())
        self.SetExecution(VolumeWeightedAveragePriceExecutionModel())
        self.averages = { }
    
    def CoarseSelectionFunction(self, universe):  
        #Main output, creating a list where the below applies
        selected = []

        #Sort by dollar volume using lambda function, declare universe as EQTY > $10
        universe = sorted(universe, key=lambda c: c.DollarVolume, reverse=True)  
        universe = [c for c in universe if c.Price > 10][:100]

        #loop for all stocks in universe, uses all coarse data
        for coarse in universe:  
            symbol = coarse.Symbol
            
            #Check for instance of SelectionData for this symbol in averages dictionary
            if symbol not in self.averages:
                # 1. Call history to get an array of 200 days of history data
                history = self.History(symbol, 200, Resolution.Daily)
                
                #2. Create new instance of SelectionData with the 'history' result
                self.averages[symbol] = SelectionData(history) 

            #Update symbol with latest coarse.AdjustedPrice data \\ accesing method and pass params
            self.averages[symbol].update(self.Time, coarse.AdjustedPrice)
            
            #Check if indicators are ready, and that the 50 day EMA is > the 200 day EMA; then add to list 'selected'
            #Access property of class as dictionary item
            if  self.averages[symbol].is_ready() and self.averages[symbol].fast > self.averages[symbol].slow:
                selected.append(symbol)
        
        #update the selected list with the top 10 results
        return selected[:10]
        
    #Method for monitoring if universe has changed
    def OnSecuritiesChanged(self, changes):
        #liquidate securities leaving the universe
        for security in changes.RemovedSecurities:
            self.Liquidate(security.Symbol)
       
       #Allocate 10% holdings to each asset added to universe
        for security in changes.AddedSecurities:
            symbol = security.Symbol
            self.SetHoldings(security.Symbol, 0.10)
            #self.log(security.Symbol + " Symbol Log")
            self.BuyPut(security.Symbol)
            
    def VIXRank(self):
        history = self.History(CBOE, self.vix, self.lookbackIV, Resolution.Daily)
        # (Current - Min) / (Max - Min)
        self.rank = ((self.Securities[self.vix].Price - min(history["low"])) / (max(history["high"]) - min(history["low"])))
 
    def OnData(self, data):
        '''OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
            Arguments:
                data: Slice object keyed by symbol containing the stock data
        '''
        if(self.IsWarmingUp):
            return
        
        # buy underlying asset
        if not self.Portfolio[self.symbol].Invested:
            self.SetHoldings(self.symbol, self.percentage)
        
        # buy put if VIX relatively high
        if self.rank > self.IVlvl:
            self.BuyPut(data)
        
        # close put before it expires
        if self.contract:
            if (self.contract.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract)
                self.Log("Closed: too close to expiration")
                self.contract = str()

    def BuyPut(self, data):
        # get option data
        if self.contract == str():
            self.contract = self.OptionsFilter(data)
            return
        
        # if not invested and option data added successfully, buy option
        elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
            self.Buy(self.contract, round(self.Portfolio[self.symbol].Quantity / self.options_alloc))

    def OptionsFilter(self, data):
        ''' OptionChainProvider gets a list of option contracts for an underlying symbol at requested date.
            Then you can manually filter the contract list returned by GetOptionContractList.
            The manual filtering will be limited to the information included in the Symbol
            (strike, expiration, type, style) and/or prices from a History call '''

        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price
        # filter the out-of-money put options from the contract list which expire close to self.DTE num of days from now
        otm_puts = [i for i in contracts if i.ID.OptionRight == OptionRight.Put and
                                            self.underlyingPrice - i.ID.StrikePrice > self.OTM * self.underlyingPrice and
                                            self.DTE - 8 < (i.ID.Date - data.Time).days < self.DTE + 8]
        if len(otm_puts) > 0:
            # sort options by closest to self.DTE days from now and desired strike, and pick first
            contract = sorted(sorted(otm_puts, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                     key = lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
            if contract not in self.contractsAdded:
                self.contractsAdded.add(contract)
                # use AddOptionContract() to subscribe the data for specified contract
                self.AddOptionContract(contract, Resolution.Minute)
            return contract
        else:
            return str()

    def Plotting(self):
        # plot IV indicator
        self.Plot("Vol Chart", "Rank", self.rank)
        # plot indicator entry level
        self.Plot("Vol Chart", "lvl", self.IVlvl)
        # plot underlying's price
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        # plot strike of put option
        
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type==SecurityType.Option]
        if option_invested:
                self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)

    def OnOrderEvent(self, orderEvent):
        # log order events
        self.Log(str(orderEvent))
        
class SelectionData():
    #3. Update the constructor to accept a history array
    def __init__(self, history):
        self.slow = ExponentialMovingAverage(200)
        self.fast = ExponentialMovingAverage(50)
        #4. Loop over the history data and update the indicators
        for bar in history.itertuples():
            self.fast.Update(bar.Index[1], bar.close)
            self.slow.Update(bar.Index[1], bar.close)
    def is_ready(self):
        return self.slow.IsReady and self.fast.IsReady
    
    def update(self, time, price):
        self.fast.Update(time, price)
        self.slow.Update(time, price)
        
        
class MaximumDrawdownPercentPerSecurityCustom(RiskManagementModel):

    def __init__(self, maximumDrawdownPercent = 0.10):
        self.maximumDrawdownPercent = -abs(maximumDrawdownPercent)
        self.liquidated = set()
        self.currentTargets = set()

    def ManageRisk(self, algorithm, targets):
        # Reset liquidated symbols on new targets
        #algorithm.Log(targets[0].Quantity)
        
        if set(targets) != self.currentTargets:
            algorithm.Log("Different")
            self.currentTargets = set(targets)
            self.liquidated = set()
        
        targets = []
        for kvp in algorithm.Securities:
            security = kvp.Value

            pnl = security.Holdings.UnrealizedProfitPercent
            if pnl < self.maximumDrawdownPercent or security.Symbol in self.liquidated:
                # liquidate
                targets.append(PortfolioTarget(security.Symbol, 0))
                if algorithm.Securities[security.Symbol].Invested:
                    self.liquidated.add(security.Symbol)
                    algorithm.Log(f"Liquidating {security.Symbol}")

        return targets
